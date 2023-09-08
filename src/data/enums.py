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
