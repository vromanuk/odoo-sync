from src.data import OrderStatusForSync

SUPPORTED_LANGUAGES = {
    "en": "English",
    "fr": "French",
    "de": "German",
    "nl": "Dutch",
    "it": "Italian",
    "tr": "Turkish",
}

ORDER_STATUSES_FOR_SYNC = [
    OrderStatusForSync.IN_PROGRESS.value,
    OrderStatusForSync.PROCESSED.value,
    OrderStatusForSync.CANCELLED_BY_ADMIN.value,
]
