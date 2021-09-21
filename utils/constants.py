from enum import Enum
from string import Template


class StateType(Enum):
    active = "active"
    archived = "archived"
    deleted = "deleted"


DEFAULT_AVATAR_URL = "https://tudo-media.ams3.digitaloceanspaces.com/profile-images/USER_IMAGE_tko5rq.png"

MIN_REQUEST_VALUE = 5000 * 100
MAX_REQUEST_VALUE = 50000 * 100

DISTANCE_MATRIX_URL = "https://maps.googleapis.com/maps/api/distancematrix/json?origins={},{}&destinations={},{}&key={}"

INITATE_TRANSFER_HEADERS = Template(
    "$from_acct_no&$narration_beneficiary&$narration_description&$to_acct_id&$to_acct_no&$to_client_id&$to_client_name&$trans_amt&$trans_ref"
)

FINALIZE_REVERSE_TRANSFER_HEADERS = Template("$transaction_id&$reference")
