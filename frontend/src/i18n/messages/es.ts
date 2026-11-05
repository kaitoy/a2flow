/** @module i18n/messages/es — The es catalog. */
import type { Messages } from "./en";

/** es messages by key. */
export const es = {
  "app.description": "Chat de IA con Google ADK",
  "errors.APPROVAL_ALREADY_RESOLVED": "Esta aprobación ya se ha decidido.",
  "errors.CONFLICT_REFERENCED":
    "Otros elementos lo siguen usando, por lo que no se puede eliminar.",
  "errors.CONFLICT_UNIQUE": "Ya existe un elemento con el mismo valor.",
  "errors.CSRF_FAILED": "No se pudo verificar tu sesión. Recarga la página e inténtalo de nuevo.",
  "errors.DEPENDENCY_CYCLE": "Las dependencias de las tareas forman un ciclo.",
  "errors.ELICITATION_ALREADY_ANSWERED": "Esta pregunta ya se ha respondido o ha caducado.",
  "errors.EMAIL_SEND_FAILED": "No se pudo enviar el correo electrónico.",
  "errors.FORBIDDEN": "No tienes permiso para hacer esto.",
  "errors.FOREIGN_KEY_VIOLATION": "No se encontró un elemento al que se hace referencia.",
  "errors.HTTP": "La solicitud falló con el estado {status}.",
  "errors.INTERNAL_ERROR": "Se produjo un error inesperado en el servidor.",
  "errors.INVALID_AGENT_SKILL": "La configuración de la skill no es válida.",
  "errors.INVALID_AVATAR": "No se puede usar la imagen de avatar.",
  "errors.INVALID_KNOWLEDGE_SOURCE": "No se puede registrar la fuente de conocimiento.",
  "errors.INVALID_MCP_SERVER": "La configuración del servidor MCP no es válida.",
  "errors.INVALID_MCP_TOOL_MOCK": "La configuración del mock de herramienta no es válida.",
  "errors.INVALID_QUERY": "No se pudo aplicar el filtro o el orden.",
  "errors.INVALID_SECRET": "La configuración del secreto no es válida.",
  "errors.INVALID_SESSION_FILE": "No se puede adjuntar el archivo a esta sesión.",
  "errors.INVALID_SESSION_INPUT": "No se puede enviar esta entrada a la sesión.",
  "errors.INVALID_SYSTEM_SETTINGS": "La configuración del sistema no es válida.",
  "errors.INVALID_TENANT": "La configuración del tenant no es válida.",
  "errors.INVALID_USER": "La configuración del usuario no es válida.",
  "errors.MCP_UNREACHABLE": "No se puede conectar con el servidor MCP.",
  "errors.NETWORK_ERROR":
    "No se puede conectar con el servidor. Comprueba tu conexión e inténtalo de nuevo.",
  "errors.NOT_FOUND": "No se encontró el elemento.",
  "errors.OUTBOUND_EMAIL_NOT_DELETABLE": "No se puede eliminar un correo que aún se está enviando.",
  "errors.REGISTRY_UNREACHABLE": "No se puede conectar con el registro MCP.",
  "errors.SECRET_RESOLUTION_FAILED": "No se pudo resolver una referencia a un secreto.",
  "errors.SESSION_AWAITING_APPROVAL": "Esta sesión está esperando una aprobación.",
  "errors.SESSION_RUN_IN_PROGRESS": "Ya hay una ejecución en curso en esta sesión.",
  "errors.SKILL_CLONE_FAILED": "No se pudo clonar el repositorio de la skill.",
  "errors.SKILL_NOT_READY": "La skill aún no tiene una revisión publicada.",
  "errors.SUMMARIZATION_FAILED": "No se pudo generar el resumen.",
  "errors.TOO_MANY_LOGIN_ATTEMPTS":
    "Demasiados intentos de inicio de sesión fallidos. Espera un momento e inténtalo de nuevo.",
  "errors.UNAUTHENTICATED": "El nombre de usuario o la contraseña no son válidos.",
  "errors.VALIDATION_ERROR": "La solicitud no es válida. Comprueba lo que has introducido.",
  "errors.WORKFLOW_NOT_DEACTIVATABLE":
    "El flujo de trabajo no está publicado, así que no hay nada que desactivar.",
  "errors.WORKFLOW_NOT_MODIFIED":
    "El flujo de trabajo no tiene cambios sin publicar que descartar.",
  "errors.WORKFLOW_NOT_RUNNABLE": "El flujo de trabajo no puede hacer esto en su estado actual.",
  "errors.WORKFLOW_PROMPT_NOT_GENERATABLE":
    "No se puede generar el prompt de este flujo de trabajo en este momento.",
  "errors.generic": "Se produjo un error. Inténtalo de nuevo.",
  "profile.language.browser": "Usar el idioma del navegador",
  "profile.language.impersonating":
    "El idioma no se puede cambiar mientras actúas como otro usuario.",
  "profile.language.label": "Idioma",
  "profile.preferences": "Preferencias",
  "time.daysAgo": "hace {count} d",
  "time.hoursAgo": "hace {count} h",
  "time.justNow": "ahora mismo",
  "time.minutesAgo": "hace {count} min",
  "users.names.superAdmin": "Superadministrador",
  "users.names.system": "Usuario del sistema",
} satisfies Messages;
