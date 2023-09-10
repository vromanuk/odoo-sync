import structlog

from .helpers import is_empty, is_unique_by, is_length_not_in_range
from .odoo_repo import OdooRepo, OdooKeys
from .ordercast_manager import OrdercastManager

logger = structlog.getLogger(__name__)


def validate_partners(
    users, odoo_repo: OdooRepo, ordercast_manager: OrdercastManager
) -> list:
    if not users:
        return []
    unique_names = set()
    has_error = False
    for user in users:
        if is_empty(user, "id"):
            logger.error(
                f"Received user with name '{user['name']}' has no remote id. Please correct it in Odoo."
            )
            has_error = True
        if is_empty(user, "name"):
            logger.error(
                f"Received user with id '{user['id']}' has no name. Please correct it in Odoo."
            )
            has_error = True
        if is_empty(user, "email"):
            logger.error(
                f"Received user with id '{user['id']}' has no email. Please correct it in Odoo."
            )
            has_error = True
        if not is_unique_by(unique_names, user, "email"):
            logger.error(
                f"Received user with email '{user['email']}' should be unique. Please correct it in Odoo (check partners which has no children or archived)."
            )
            has_error = True
        if "name" in user and is_length_not_in_range(user["name"], 1, 150):
            logger.error(
                f"Received user with name '{user['name']}' has more than max 150 symbols. Please correct it in Odoo."
            )
            has_error = True

        # exists_by_email = User.all_objects.filter(email=user["email"]).first()
        ordercast_user = ordercast_manager.get_user_by_email(user["email"])
        if ordercast_user:
            # existing_external_object = UserExternal.all_objects.filter(
            #     user_id=exists_by_email.id
            # ).first()
            odoo_user = odoo_repo.get(key=OdooKeys.USERS, entity_id=ordercast_user.id)
            if odoo_user and odoo_user.odoo_id != user["id"]:
                logger.error(
                    f"Received user with email '{user['email']}' already exists locally and it's Odoo id is '{odoo_user.odoo_id}' and name is '{ordercast_user.name}' coming Odoo id is '{user['id']}' and name is '{user['name']}'. Please give the another email to this '{user['name']}' partner in Odoo (check partners which has no children or archived)."
                )
                has_error = True
            elif ordercast_user.name != user["name"]:
                logger.error(
                    f"Received user with email '{user['email']}' already exists locally, but not synced with Odoo. Please give the another email to this '{user['name']}' partner in Odoo (check partners which has no children or archived)."
                )
                has_error = True
    if has_error:
        raise RuntimeError(
            "User has errors. Please correct them in Odoo and try to sync again."
        )
