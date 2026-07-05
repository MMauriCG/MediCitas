"""
MediCitas - Sistema de Asistencia Médica
Uso: python3 medicitas.py
Sistema completo de gestión médica:
- Pacientes
- Citas
- Agenda semanal
- Estados de citas
- SQLite integrado
- Sin dependencias externas
"""

import sqlite3
import os
import inspect
import re
import getpass
import hashlib

from datetime import date, datetime, timedelta
from dataclasses import dataclass, field
from typing import Optional
from enum import Enum

# ─────────────────────────────────────────────────────────────
# SEGURIDAD / ROLES DE ACCESO
# ─────────────────────────────────────────────────────────────

class Rol(str, Enum):
    ADMIN = "admin"
    RECEPCIONISTA = "recepcionista"


USUARIOS = {
    "admin": {
        "password_hash": hashlib.sha256("admin123".encode()).hexdigest(),
        "rol": Rol.ADMIN
    },
    "recepcion": {
        "password_hash": hashlib.sha256("recepcion123".encode()).hexdigest(),
        "rol": Rol.RECEPCIONISTA
    }
}


def login():
    """Solicita usuario y contraseña antes de entrar al sistema."""
    print("INICIO DE SESIÓN")
    print("----------------")

    usuario = input("Usuario: ").strip()
    password = getpass.getpass("Contraseña: ")

    if usuario not in USUARIOS:
        raise ValueError("Usuario o contraseña incorrectos")

    password_hash = hashlib.sha256(password.encode()).hexdigest()

    if password_hash != USUARIOS[usuario]["password_hash"]:
        raise ValueError("Usuario o contraseña incorrectos")

    return {
        "usuario": usuario,
        "rol": USUARIOS[usuario]["rol"]
    }


def requiere_rol(usuario_actual, roles_permitidos):
    """Valida que el usuario tenga uno de los roles permitidos."""
    if usuario_actual["rol"] not in roles_permitidos:
        raise PermissionError("No tienes permisos para realizar esta acción")


# ─────────────────────────────────────────────────────────────
# ENUMS
# ─────────────────────────────────────────────────────────────
# Define los tipos de cita permitidos en el sistema.
class TipoCita(str, Enum):
    # Representa una cita de consulta general.
    CONSULTA = "consulta"
    # Representa una cita de seguimiento.
    SEGUIMIENTO = "seguimiento"
    # Representa una cita de emergencia.
    EMERGENCIA = "emergencia"
    # Representa una cita de chequeo rutinario.
    CHEQUEO = "chequeo"
    # Representa una cita relacionada con laboratorio.
    LABORATORIO = "laboratorio"
    # Representa cualquier otro tipo de cita no contemplado arriba.
    OTRO = "otro"

# Define los posibles estados que puede tener una cita.
class EstadoCita(str, Enum):
    # Indica que la cita ha sido agendada pero aún no ocurre.
    PROGRAMADA = "programada"
    # Indica que la cita ya fue atendida.
    COMPLETADA = "completada"
    # Indica que la cita fue cancelada.
    CANCELADA = "cancelada"

# ─────────────────────────────────────────────────────────────
# MODELOS
# ─────────────────────────────────────────────────────────────
# Convierte esta clase en un dataclass para generar automáticamente métodos útiles como __init__.
@dataclass
class Paciente:
    # Identificador único del paciente.
    id: int
    # Nombre del paciente.
    nombre: str
    # Apellido del paciente.
    apellido: str
    # Correo electrónico del paciente.
    email: str
    # Número de teléfono del paciente.
    telefono: str
    # Fecha de nacimiento del paciente.
    fecha_nacimiento: date
    # Historial o información clínica del paciente; puede no existir.
    historia_clinica: Optional[str] = None
    # Notas adicionales del paciente; puede no existir.
    notas: Optional[str] = None
    # Fecha y hora de creación del registro; se asigna automáticamente al crear la instancia.
    creado_en: datetime = field(default_factory=datetime.now)

    # Define una propiedad para obtener el nombre completo sin llamarla como método.
    @property
    def nombre_completo(self):
        # Retorna el nombre y apellido concatenados en una sola cadena.
        return f"{self.nombre} {self.apellido}"

    # Método que calcula la edad actual del paciente.
    def edad(self):
        # Obtiene la fecha actual del sistema.
        hoy = date.today()
        # Calcula la edad restando el año actual menos el año de nacimiento.
        # Luego ajusta restando 1 si todavía no ha cumplido años en el año actual.
        return (
            hoy.year
            - self.fecha_nacimiento.year
            - (
                # Esta comparación devuelve True (equivale a 1) si la fecha actual
                # aún está antes del cumpleaños de este año.
                (hoy.month, hoy.day)
                < (
                    self.fecha_nacimiento.month,
                    self.fecha_nacimiento.day
                )
            )
        )

# Convierte esta clase en un dataclass para representar una cita médica.
@dataclass
class Cita:
    # Identificador único de la cita.
    id: int
    # Identificador del paciente asociado a la cita.
    paciente_id: int
    # Fecha en que se realizará la cita.
    fecha: date
    # Hora programada de la cita.
    hora: str
    # Duración de la cita en minutos.
    duracion_minutos: int
    # Tipo de cita, usando el enum TipoCita.
    tipo: TipoCita
    # Estado actual de la cita, usando el enum EstadoCita.
    estado: EstadoCita
    # Nombre del paciente asociado; por defecto se inicializa vacío.
    nombre_paciente: str = ""
    # Nombre del médico asignado; puede no existir.
    medico: Optional[str] = None
    # Notas adicionales de la cita; puede no existir.
    notas: Optional[str] = None
    # Fecha y hora de creación de la cita; se asigna automáticamente.
    creado_en: datetime = field(default_factory=datetime.now)
# ─────────────────────────────────────────────────────────────
# BASE DE DATOS
# ─────────────────────────────────────────────────────────────
# Define una clase para encapsular la conexión y operaciones básicas de la base de datos.
class BaseDatos:
    # Constructor de la clase; recibe la ruta del archivo de base de datos.
    def __init__(self, ruta="medicitas.db"):
        # Crea una conexión a la base de datos SQLite usando la ruta indicada.
        self.conn = sqlite3.connect(ruta)
        # Configura la conexión para que las filas puedan accederse por nombre de columna.
        self.conn.row_factory = sqlite3.Row
        # Activa el soporte de claves foráneas en SQLite para respetar relaciones entre tablas.
        self.conn.execute("PRAGMA foreign_keys = ON")
        # Llama al método que crea las tablas si todavía no existen.
        self.crear_tablas()

    # Método encargado de crear la estructura de tablas de la base de datos.
    def crear_tablas(self):
        # Ejecuta un script SQL con múltiples sentencias de creación de tablas.
        self.conn.executescript("""
        CREATE TABLE IF NOT EXISTS pacientes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT NOT NULL,
            apellido TEXT NOT NULL,
            email TEXT NOT NULL UNIQUE,
            telefono TEXT NOT NULL,
            fecha_nacimiento TEXT NOT NULL,
            historia_clinica TEXT,
            notas TEXT,
            creado_en TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS citas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            paciente_id INTEGER NOT NULL,
            fecha TEXT NOT NULL,
            hora TEXT NOT NULL,
            duracion_minutos INTEGER DEFAULT 30,
            tipo TEXT DEFAULT 'consulta',
            estado TEXT DEFAULT 'programada',
            medico TEXT,
            notas TEXT,
            creado_en TEXT DEFAULT (datetime('now')),

            FOREIGN KEY (paciente_id)
            REFERENCES pacientes(id)
            ON DELETE CASCADE
        );
        """)
        # Guarda de forma permanente los cambios realizados en la base de datos.
        self.conn.commit()

    # Método para cerrar la conexión con la base de datos cuando ya no se necesite.
    def cerrar(self):
        # Cierra la conexión abierta con SQLite.
        self.conn.close()
# ─────────────────────────────────────────────────────────────
# REPO PACIENTES
# ─────────────────────────────────────────────────────────────
# Define el repositorio encargado de las operaciones CRUD relacionadas con pacientes.
class RepoPacientes:
    # Inicializa el repositorio recibiendo una instancia de base de datos.
    def __init__(self, db):
        # Guarda la referencia a la base de datos para reutilizar la conexión en los métodos.
        self.db = db

    # Crea un nuevo paciente en la base de datos con los datos recibidos.
    def crear(
        self,
        nombre,
        apellido,
        email,
        telefono,
        fecha_nacimiento,
        historia_clinica=None,
        notas=None
    ):
        # Ejecuta una sentencia INSERT para almacenar un nuevo registro en la tabla pacientes.
        cur = self.db.conn.execute(
            """
            INSERT INTO pacientes
            (
                nombre,
                apellido,
                email,
                telefono,
                fecha_nacimiento,
                historia_clinica,
                notas
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                # Pasa el nombre del paciente como primer parámetro del INSERT.
                nombre,
                # Pasa el apellido del paciente como segundo parámetro.
                apellido,
                # Pasa el correo electrónico del paciente.
                email,
                # Pasa el teléfono del paciente.
                telefono,
                # Convierte la fecha de nacimiento a texto para almacenarla en formato ISO.
                str(fecha_nacimiento),
                # Pasa la historia clínica si fue proporcionada.
                historia_clinica,
                # Pasa las notas adicionales si existen.
                notas
            )
        )
        # Confirma los cambios en la base de datos para guardar el nuevo registro.
        self.db.conn.commit()
        # Devuelve el paciente recién creado consultándolo por el id generado automáticamente.
        return self.obtener(cur.lastrowid)

    # Obtiene la lista completa de pacientes ordenados por apellido y nombre.
    def listar(self):
        # Ejecuta una consulta para recuperar todos los pacientes de la tabla.
        rows = self.db.conn.execute(
            """
            SELECT *
            FROM pacientes
            ORDER BY apellido, nombre
            """
        ).fetchall()
        # Convierte cada fila recuperada en un objeto Paciente usando el método mapear.
        return [self.mapear(r) for r in rows]

    # Busca un paciente específico usando su identificador.
    def obtener(self, id_paciente):
        # Ejecuta una consulta para obtener una sola fila cuyo id coincida con el proporcionado.
        row = self.db.conn.execute(
            """
            SELECT *
            FROM pacientes
            WHERE id = ?
            """,
            # Envía el id como una tupla de un solo elemento para parametrizar la consulta.
            (id_paciente,)
        ).fetchone()
        # Si se encontró una fila, la convierte en un objeto Paciente y la retorna.
        if row:
            return self.mapear(row)
        # Si no existe el paciente, retorna None.
        return None

    # Elimina un paciente según su id.
    def eliminar(self, id_paciente):
        # Ejecuta una sentencia DELETE para borrar el registro correspondiente.
        cur = self.db.conn.execute(
            """
            DELETE FROM pacientes
            WHERE id = ?
            """,
            # Pasa el id del paciente que se desea eliminar.
            (id_paciente,)
        )
        # Confirma la eliminación en la base de datos.
        self.db.conn.commit()
        # Retorna True si se eliminó al menos una fila; en caso contrario retorna False.
        return cur.rowcount > 0

    # Convierte una fila de la base de datos en una instancia del modelo Paciente.
    def mapear(self, r):
        # Crea y retorna un objeto Paciente usando los valores de la fila recibida.
        return Paciente(
            # Asigna el id del registro al atributo id del objeto.
            id=r["id"],
            # Asigna el nombre almacenado en la base de datos.
            nombre=r["nombre"],
            # Asigna el apellido almacenado en la base de datos.
            apellido=r["apellido"],
            # Asigna el correo electrónico del paciente.
            email=r["email"],
            # Asigna el número de teléfono.
            telefono=r["telefono"],
            # Convierte la fecha de nacimiento desde texto ISO a un objeto date.
            fecha_nacimiento=date.fromisoformat(
                r["fecha_nacimiento"]
            ),
            # Asigna la historia clínica tal como fue recuperada.
            historia_clinica=r["historia_clinica"],
            # Asigna las notas adicionales del paciente.
            notas=r["notas"],
            # Convierte la fecha de creación desde texto ISO a un objeto datetime.
            creado_en=datetime.fromisoformat(
                r["creado_en"]
            )
        )
# ─────────────────────────────────────────────────────────────
# REPO CITAS
# ─────────────────────────────────────────────────────────────
# Define el repositorio encargado de gestionar las operaciones CRUD de las citas.
class RepoCitas:
    # Inicializa el repositorio con una referencia a la base de datos.
    def __init__(self, db):
        # Guarda la instancia de base de datos para usar su conexión en los métodos.
        self.db = db

    # Crea una nueva cita en la base de datos con los datos recibidos.
    def crear(
        self,
        paciente_id,
        fecha,
        hora,
        duracion_minutos,
        tipo,
        medico=None,
        notas=None
    ):
        # Ejecuta una sentencia INSERT para registrar una nueva cita.
        cur = self.db.conn.execute(
            """
            INSERT INTO citas
            (
                paciente_id,
                fecha,
                hora,
                duracion_minutos,
                tipo,
                estado,
                medico,
                notas
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                # Pasa el id del paciente relacionado con la cita.
                paciente_id,
                # Convierte la fecha a texto para almacenarla en formato compatible con SQLite.
                str(fecha),
                # Pasa la hora de la cita.
                hora,
                # Pasa la duración programada de la cita en minutos.
                duracion_minutos,
                # Guarda el valor textual del tipo de cita.
                tipo.value,
                # Asigna por defecto el estado programada al crear la cita.
                EstadoCita.PROGRAMADA.value,
                # Pasa el nombre del médico si se proporcionó.
                medico,
                # Pasa las notas adicionales de la cita si existen.
                notas
            )
        )
        # Confirma los cambios para guardar la nueva cita en la base de datos.
        self.db.conn.commit()
        # Devuelve la cita recién creada consultándola mediante el id generado automáticamente.
        return self.obtener(cur.lastrowid)

    # Lista todas las citas junto con el nombre completo del paciente asociado.
    def listar(self):
        # Ejecuta una consulta que une citas con pacientes para enriquecer el resultado.
        rows = self.db.conn.execute(
            """
            SELECT
                c.*,
                p.nombre || ' ' || p.apellido AS nombre_paciente
            FROM citas c
            JOIN pacientes p
                ON p.id = c.paciente_id
            ORDER BY c.fecha, c.hora
            """
        ).fetchall()
        # Convierte cada fila obtenida en un objeto Cita usando el método mapear.
        return [self.mapear(r) for r in rows]

    # Obtiene una cita específica por su identificador.
    def obtener(self, id_cita):
        # Ejecuta una consulta que recupera la cita y el nombre completo del paciente relacionado.
        row = self.db.conn.execute(
            """
            SELECT
                c.*,
                p.nombre || ' ' || p.apellido AS nombre_paciente
            FROM citas c
            JOIN pacientes p
                ON p.id = c.paciente_id
            WHERE c.id = ?
            """,
            # Envía el id de la cita como parámetro de la consulta.
            (id_cita,)
        ).fetchone()
        # Si la cita existe, convierte la fila en un objeto Cita y la retorna.
        if row:
            return self.mapear(row)
        # Si no se encuentra ninguna coincidencia, retorna None.
        return None

    # Actualiza el estado de una cita existente.
    def actualizar_estado(self, id_cita, estado):
        # Ejecuta una sentencia UPDATE para modificar el estado de la cita indicada.
        self.db.conn.execute(
            """
            UPDATE citas
            SET estado = ?
            WHERE id = ?
            """,
            (
                # Usa el valor textual del enum de estado recibido.
                estado.value,
                # Indica qué cita debe actualizarse mediante su id.
                id_cita
            )
        )
        # Confirma el cambio realizado en la base de datos.
        self.db.conn.commit()

    # Elimina una cita específica según su id.
    def eliminar(self, id_cita):
        # Ejecuta una sentencia DELETE para borrar la cita correspondiente.
        cur = self.db.conn.execute(
            """
            DELETE FROM citas
            WHERE id = ?
            """,
            # Pasa el id de la cita que se desea eliminar.
            (id_cita,)
        )
        # Confirma la eliminación en la base de datos.
        self.db.conn.commit()
        # Retorna True si se eliminó alguna fila; si no, retorna False.
        return cur.rowcount > 0

    # Convierte una fila de resultados en una instancia del modelo Cita.
    def mapear(self, r):
        # Crea y devuelve un objeto Cita a partir de los datos recuperados.
        return Cita(
            # Asigna el id de la cita.
            id=r["id"],
            # Asigna el id del paciente asociado.
            paciente_id=r["paciente_id"],
            # Convierte la fecha desde texto ISO a un objeto date.
            fecha=date.fromisoformat(r["fecha"]),
            # Asigna la hora registrada para la cita.
            hora=r["hora"],
            # Asigna la duración de la cita en minutos.
            duracion_minutos=r["duracion_minutos"],
            # Convierte el valor almacenado a un miembro del enum TipoCita.
            tipo=TipoCita(r["tipo"]),
            # Convierte el valor almacenado a un miembro del enum EstadoCita.
            estado=EstadoCita(r["estado"]),
            # Asigna el nombre completo del paciente calculado en la consulta SQL.
            nombre_paciente=r["nombre_paciente"],
            # Asigna el médico relacionado con la cita.
            medico=r["medico"],
            # Asigna las notas adicionales de la cita.
            notas=r["notas"],
            # Convierte la fecha y hora de creación desde texto ISO a un objeto datetime.
            creado_en=datetime.fromisoformat(
                r["creado_en"]
            )
        )
# ─────────────────────────────────────────────────────────────
# SERVICIO
# ─────────────────────────────────────────────────────────────
# Define una clase que centraliza el acceso a la base de datos, pacientes y citas.
class ServicioMedico:
    # Inicializa el servicio médico y prepara sus componentes principales.
    def __init__(self):
        # Crea una instancia de la base de datos para gestionar la persistencia.
        self.db = BaseDatos()
        # Crea el repositorio de pacientes usando la conexión de la base de datos.
        self.pacientes = RepoPacientes(self.db)
        # Crea el repositorio de citas usando la misma base de datos.
        self.citas = RepoCitas(self.db)

    # Cierra correctamente los recursos utilizados por el servicio.
    def cerrar(self):
        # Cierra la conexión con la base de datos a través del objeto db.
        self.db.cerrar()

# ─────────────────────────────────────────────────────────────
# UTILIDADES
# ─────────────────────────────────────────────────────────────
# Limpia la pantalla de la consola según el sistema operativo detectado.
def limpiar():
    # Ejecuta el comando 'cls' en Windows o 'clear' en sistemas tipo Unix.
    os.system("cls" if os.name == "nt" else "clear")

# Imprime una línea separadora opcionalmente acompañada de un título.
def separador(titulo=""):
    # Imprime una línea en blanco seguida de una barra visual de separación.
    print("" + "=" * 60)
    # Si se proporcionó un título, lo imprime en mayúsculas.
    if titulo:
        print(titulo.upper())
    # Imprime la línea inferior del separador.
    print("=" * 60)

# Solicita al usuario un texto desde consola y valida si es obligatorio.
def pedir(texto, requerido=True):
    # Mantiene la solicitud hasta que el valor sea válido.
    while True:
        # Muestra el mensaje, lee la entrada y elimina espacios al inicio y al final.
        valor = input(f"{texto}: ").strip()
        # Si el usuario ingresó algo o el campo no es obligatorio, devuelve el valor.
        if valor or not requerido:
            return valor
        # Informa que el campo es obligatorio cuando no se ingresó nada.
        print("Campo obligatorio")

# Solicita un número entero al usuario y lo valida.
def pedir_int(texto):
    # Repite la solicitud hasta recibir un entero válido.
    while True:
        try:
            # Lee el valor ingresado, lo convierte a entero y lo devuelve.
            return int(input(f"{texto}: "))
        except:
            # Si la conversión falla, informa al usuario del error.
            print("Debe ser un número")

# Solicita una fecha al usuario con formato ISO y la valida.
def pedir_fecha(texto):
    # Repite la solicitud hasta que la fecha ingresada sea correcta.
    while True:
        try:
            # Lee la cadena de fecha con formato AAAA-MM-DD y la convierte a un objeto date.
            return date.fromisoformat(
                input(f"{texto} (AAAA-MM-DD): ")
            )
        except:
            # Muestra un mensaje si la fecha no tiene el formato esperado o es inválida.
            print("Fecha inválida")

# ─────────────────────────────────────────────────────────────
# IMPRESIONES
# ─────────────────────────────────────────────────────────────
# Imprime en consola la información principal de un paciente.
def imprimir_paciente(p):
    # Imprime el id y el nombre completo del paciente.
    print(f"[{p.id}] {p.nombre_completo}")
    # Imprime la edad actual del paciente calculada por su método edad().
    print(f"Edad: {p.edad()} años")
    # Imprime el correo electrónico del paciente.
    print(f"Email: {p.email}")
    # Imprime el número de teléfono del paciente.
    print(f"Teléfono: {p.telefono}")
    # Si el paciente tiene notas registradas, las muestra en pantalla.
    if p.notas:
        print(f"Notas: {p.notas}")

# Imprime en consola la información principal de una cita.
def imprimir_cita(c):
    # Imprime id, fecha, hora y nombre del paciente asociado a la cita.
    print(
        f"[{c.id}] {c.fecha} {c.hora} "
        f"- {c.nombre_paciente}"
    )
    # Imprime el tipo de la cita.
    print(f"Tipo: {c.tipo.value}")
    # Imprime el estado actual de la cita.
    print(f"Estado: {c.estado.value}")
    # Si la cita tiene médico asignado, lo muestra.
    if c.medico:
        print(f"Médico: {c.medico}")
    # Si la cita tiene notas asociadas, las imprime.
    if c.notas:
        print(f"Notas: {c.notas}")
# ─────────────────────────────────────────────────────────────
# MENÚ PACIENTES
# ─────────────────────────────────────────────────────────────
# Define el menú interactivo para gestionar pacientes desde consola.
def menu_pacientes(srv):

    # Inicia un bucle infinito para mantener el menú activo hasta que el usuario decida salir.
    while True:
        # Muestra un separador con el título del módulo actual.
        separador("Pacientes")
        # Imprime la opción para listar pacientes.
        print("1. Listar")
        # Imprime la opción para crear un nuevo paciente.
        print("2. Crear")
        # Imprime la opción para eliminar un paciente existente.
        print("3. Eliminar")
        # Imprime la opción para volver al menú anterior.
        print("0. Volver")
        # Solicita al usuario que elija una opción.
        op = pedir("Opción")
        # Si el usuario elige listar, obtiene y muestra todos los pacientes.
        if op == "1":
            # Recupera la lista de pacientes desde el servicio.
            pacientes = srv.pacientes.listar()
            # Recorre cada paciente recuperado.
            for p in pacientes:
                # Imprime los datos del paciente actual.
                imprimir_paciente(p)
                # Imprime una línea separadora entre pacientes.
                print("-" * 40)
        # Si el usuario elige crear, solicita los datos y registra un nuevo paciente.
        elif op == "2":
            try:
                # Llama al repositorio para crear el paciente con los datos ingresados por consola.
                paciente = srv.pacientes.crear(
                    # Solicita el nombre del paciente.
                    nombre=pedir("Nombre"),
                    # Solicita el apellido del paciente.
                    apellido=pedir("Apellido"),
                    # Solicita el correo electrónico del paciente.
                    email=pedir("Email"),
                    # Solicita el teléfono del paciente.
                    telefono=pedir("Teléfono"),
                    # Solicita y valida la fecha de nacimiento.
                    fecha_nacimiento=pedir_fecha(
                        "Fecha nacimiento"
                    ),
                    # Solicita la historia clínica; si queda vacía, guarda None.
                    historia_clinica=pedir(
                        "Historia clínica",
                        False
                    ) or None,
                    # Solicita notas opcionales; si queda vacío, guarda None.
                    notas=pedir(
                        "Notas",
                        False
                    ) or None
                )
                # Informa que el paciente fue creado y muestra su id.
                print(f"Paciente creado ID {paciente.id}")
            except Exception as e:
                # Captura cualquier error durante la creación y lo muestra en pantalla.
                print(f"Error: {e}")
        # Si el usuario elige eliminar, solicita el id y lo elimina si existe.
        elif op == "3":
            # Solicita el identificador numérico del paciente.
            id_p = pedir_int("ID paciente")
            # Intenta eliminar el paciente indicado.
            ok = srv.pacientes.eliminar(id_p)
            # Si la eliminación fue exitosa, informa al usuario.
            if ok:
                print("Paciente eliminado")
            # Si no se encontró el paciente, avisa al usuario.
            else:
                print("No encontrado")
        # Si el usuario elige volver, sale del bucle y regresa al menú anterior.
        elif op == "0":
            break
        # Espera a que el usuario presione Enter antes de continuar.
        input("Enter para continuar...")
# ─────────────────────────────────────────────────────────────
# VALIDACIONES / EXPRESIONES REGULARES
# ─────────────────────────────────────────────────────────────

REGEX_NOMBRE = r"^[A-Za-zÁÉÍÓÚáéíóúÑñ ]{2,50}$"
REGEX_TELEFONO = r"^[0-9+ ]{8,15}$"
REGEX_HORA = r"^([01]\d|2[0-3]):[0-5]\d$"
REGEX_EMAIL = r"^[\w\.-]+@[\w\.-]+\.\w{2,}$"


def validar_nombre(valor, campo="Campo"):
    valor = valor.strip()

    if not re.match(REGEX_NOMBRE, valor):
        raise ValueError(
            f"{campo} inválido. Solo se permiten letras, espacios y tildes."
        )

    return valor


def validar_telefono(valor):
    valor = valor.strip()

    if not re.match(REGEX_TELEFONO, valor):
        raise ValueError(
            "Teléfono inválido. Solo se permiten números, espacios y el símbolo +."
        )

    return valor


def validar_email(valor):
    valor = valor.strip()

    if not re.match(REGEX_EMAIL, valor):
        raise ValueError("Correo electrónico inválido.")

    return valor


def validar_hora(valor):
    valor = valor.strip()

    if not re.match(REGEX_HORA, valor):
        raise ValueError("Hora inválida. Use formato HH:MM, por ejemplo 09:30.")

    return valor


def validar_notas(valor):
    if valor is None:
        return None

    valor = valor.strip()

    if valor == "":
        return None

    # Se bloquean caracteres potencialmente riesgosos o innecesarios en campos de texto libre.
    if re.search(r"[<>{};]", valor):
        raise ValueError(
            "El texto contiene caracteres no permitidos: < > { } ;"
        )

    if len(valor) > 300:
        raise ValueError("El texto no puede superar los 300 caracteres.")

    return valor


def validar_entero_positivo(valor, campo="Número"):
    try:
        numero = int(valor)
    except ValueError:
        raise ValueError(f"{campo} debe ser un número entero.")

    if numero <= 0:
        raise ValueError(f"{campo} debe ser mayor que cero.")

    return numero


def validar_duracion(valor):
    numero = validar_entero_positivo(valor, "Duración")

    if numero > 240:
        raise ValueError("La duración no puede superar los 240 minutos.")

    return numero


# ─────────────────────────────────────────────────────────────
# MENÚ CITAS MODIFICADO
# Reemplaza tu función menu_citas original por esta.
# ─────────────────────────────────────────────────────────────

def menu_citas(srv, usuario_actual):
    while True:
        try:
            separador("Citas")

            print("1. Listar")
            print("2. Crear")
            print("3. Completar")
            print("4. Cancelar")
            print("5. Eliminar")
            print("0. Volver")

            op = pedir("Opción")

            if op == "1":
                citas = srv.citas.listar()

                if not citas:
                    print("\nNo hay citas registradas.")

                for c in citas:
                    imprimir_cita(c)
                    print("-" * 40)

            elif op == "2":
                requiere_rol(
                    usuario_actual,
                    [Rol.ADMIN, Rol.RECEPCIONISTA]
                )

                paciente_id = pedir_int("ID paciente")
                fecha = pedir_fecha("Fecha")
                hora = validar_hora(pedir("Hora HH:MM"))
                duracion = validar_duracion(pedir("Duración minutos"))

                tipo_texto = pedir(
                    "Tipo "
                    "(consulta/seguimiento/emergencia/chequeo/laboratorio/otro)"
                ).lower().strip()

                tipo = TipoCita(tipo_texto)

                medico_input = pedir("Médico", False)
                notas_input = pedir("Notas", False)

                medico = validar_notas(medico_input)
                notas = validar_notas(notas_input)

                cita = srv.citas.crear(
                    paciente_id=paciente_id,
                    fecha=fecha,
                    hora=hora,
                    duracion_minutos=duracion,
                    tipo=tipo,
                    medico=medico,
                    notas=notas
                )

                print(f"\nCita creada correctamente. ID: {cita.id}")

            elif op == "3":
                requiere_rol(usuario_actual, [Rol.ADMIN])

                id_cita = pedir_int("ID cita")

                srv.citas.actualizar_estado(
                    id_cita,
                    EstadoCita.COMPLETADA
                )

                print("\nCita completada correctamente.")

            elif op == "4":
                requiere_rol(
                    usuario_actual,
                    [Rol.ADMIN, Rol.RECEPCIONISTA]
                )

                id_cita = pedir_int("ID cita")

                srv.citas.actualizar_estado(
                    id_cita,
                    EstadoCita.CANCELADA
                )

                print("\nCita cancelada correctamente.")

            elif op == "5":
                requiere_rol(usuario_actual, [Rol.ADMIN])

                id_cita = pedir_int("ID cita")

                ok = srv.citas.eliminar(id_cita)

                if ok:
                    print("\nCita eliminada correctamente.")
                else:
                    print("\nNo encontrada.")

            elif op == "0":
                break

            else:
                print("\nOpción inválida.")

        except PermissionError as e:
            print(f"\nAcceso denegado: {e}")

        except ValueError as e:
            print(f"\nError de validación: {e}")

        except Exception as e:
            print(f"\nError inesperado: {e}")

        input("\nEnter para continuar...")

def abrir_menu_pacientes(srv, usuario_actual):
    parametros = inspect.signature(menu_pacientes).parameters

    if len(parametros) == 1:
        menu_pacientes(srv)
    else:
        menu_pacientes(srv, usuario_actual)
# ─────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────

def main():
    srv = None

    try:
        limpiar()
        usuario_actual = login()

        srv = ServicioMedico()

        while True:
            limpiar()
            separador(
                f"MediCitas - Usuario: {usuario_actual['usuario']} "
                f"({usuario_actual['rol'].value})"
            )

            print("1. Pacientes")
            print("2. Citas")
            print("0. Salir")

            op = pedir("Opción")

            if op == "1":
                abrir_menu_pacientes(srv, usuario_actual)

            elif op == "2":
                menu_citas(srv, usuario_actual)

            elif op == "0":
                print("\nIngreso Finalizado")
                break

            else:
                print("\nOpción inválida")
                input("\nEnter para continuar...")

    except ValueError as e:
        print(f"\nError de autenticación: {e}")

    except Exception as e:
        print(f"\nError crítico de la aplicación: {e}")

    finally:
        if srv is not None:
            srv.cerrar()


if __name__ == "__main__":
    main()
