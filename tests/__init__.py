from bot.handlers.menu import AddFlow
from bot.handlers.reminders import DigestForm
from bot.handlers.schedule import ScheduleForm
from bot.handlers.tasks import TaskForm
from bot.texts import (
    BTN_ADD,
    BTN_ADMIN,
    BTN_CANCEL,
    BTN_DIGEST,
    BTN_SCHEDULE,
    BTN_SKIP,
    BTN_TASKS,
)

# Reply-menu labels used by handlers (must stay unique)
MENU_BUTTONS = {BTN_TASKS, BTN_SCHEDULE, BTN_ADD, BTN_DIGEST, BTN_ADMIN, BTN_CANCEL, BTN_SKIP}

# FSM groups present in the app
FSM_GROUPS = (TaskForm, ScheduleForm, DigestForm, AddFlow)
