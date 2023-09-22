import enum


class CategoryType(str, enum.Enum):
    CLASS = "Class"
    CATALOG = "Catalog"
    PRODUCT_ATTRIBUTE = "Product Attribute"


class OrderStatus(str, enum.Enum):
    # quotation
    DRAFT_STATUS = "draft"
    # quotation sent
    SENT_STATUS = "sent"
    # Sales order
    SALE_STATUS = "sale"
    # locked
    DONE_STATUS = "done"
    # cancelled
    CANCEL_STATUS = "cancel"

    SUBMITTED_STATUS = "submitted"
    PENDING_PAYMENT_STATUS = "pending_payment"
    IN_PROGRESS_STATUS = "in_progress"
    PROCESSED_STATUS = "processed"
    COMPLETED_STATUS = "completed"
    CANCELLED_BY_CLIENT_STATUS = "client_canceled"
    CANCELLED_BY_ADMIN_STATUS = "admin_canceled"


class OrderStatusForSync(enum.Enum):
    IN_PROGRESS = 1
    PROCESSED = 3
    CANCELLED_BY_ADMIN = 6


class InvoiceStatus(str, enum.Enum):
    INV_NO_STATUS = "no"
    INV_TO_INVOICE_STATUS = "to invoice"
    INV_INVOICED_STATUS = "invoiced"
    INV_UPSELLING_STATUS = "upselling"


class UserStatus(str, enum.Enum):
    NEW = "new"
    APPROVED = "approved"
    DEACTIVATED = "deactivated"
    REFUSED = "refused"


class PartnerType(str, enum.Enum):
    USER = "user"
    ADDRESS = "address"


class PartnerAddressType(str, enum.Enum):
    CONTACT = "contact"
    INVOICE = "invoice"
    DELIVERY = "delivery"
    OTHER = "other"
    PRIVATE = "private"


class Locale(str, enum.Enum):
    DE = "de"
    EN = "en"
    ES = "es"
    FR = "fr"
    IT = "it"
    NL = "nl"
    RU = "ru"
    TR = "tr"
    UK = "uk"
