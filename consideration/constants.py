from enum import Enum, auto
from web3.constants import ADDRESS_ZERO

CONSIDERATION_CONTRACT_NAME = "Consideration"
CONSIDERATION_CONTRACT_VERSION = "rc.1"
EIP_712_ORDER_TYPE = {
    "EIP712Domain": [
        {"name": "name", "type": "string"},
        {"name": "version", "type": "string"},
        {"name": "chainId", "type": "uint256"},
        {"name": "verifyingContract", "type": "address"},
    ],
    "OrderComponents": [
        {"name": "offerer", "type": "address"},
        {"name": "zone", "type": "address"},
        {"name": "offer", "type": "OfferItem[]"},
        {"name": "consideration", "type": "ConsiderationItem[]"},
        {"name": "orderType", "type": "uint8"},
        {"name": "startTime", "type": "uint256"},
        {"name": "endTime", "type": "uint256"},
        {"name": "zoneHash", "type": "bytes32"},
        {"name": "salt", "type": "uint256"},
        {"name": "conduit", "type": "address"},
        {"name": "nonce", "type": "uint256"},
    ],
    "OfferItem": [
        {"name": "itemType", "type": "uint8"},
        {"name": "token", "type": "address"},
        {"name": "identifierOrCriteria", "type": "uint256"},
        {"name": "startAmount", "type": "uint256"},
        {"name": "endAmount", "type": "uint256"},
    ],
    "ConsiderationItem": [
        {"name": "itemType", "type": "uint8"},
        {"name": "token", "type": "address"},
        {"name": "identifierOrCriteria", "type": "uint256"},
        {"name": "startAmount", "type": "uint256"},
        {"name": "endAmount", "type": "uint256"},
        {"name": "recipient", "type": "address"},
    ],
}


class OrderType(Enum):
    FULL_OPEN = 0  # No partial fills, anyone can execute
    PARTIAL_OPEN = 1  # Partial fills supported, anyone can execute
    FULL_RESTRICTED = 2  # No partial fills, only offerer or zone can execute
    PARTIAL_RESTRICTED = 3  # Partial fills supported, only offerer or zone can execute


class ItemType(Enum):
    NATIVE = 0
    ERC20 = 1
    ERC721 = 2
    ERC1155 = 3
    ERC721_WITH_CRITERIA = 4
    ERC1155_WITH_CRITERIA = 5


class Side(Enum):
    OFFER = 0
    CONSIDERATION = 1


class BasicOrderRouteType(Enum):
    ETH_TO_ERC721 = 0
    ETH_TO_ERC1155 = 1
    ERC20_TO_ERC721 = 2
    ERC20_TO_ERC1155 = 4
    ERC721_TO_ERC20 = 5
    ERC1155_TO_ERC20 = 6


class ProxyStrategy(Enum):
    IF_ZERO_APPROVALS_NEEDED = auto()
    NEVER = auto()
    ALWAYS = auto()


MAX_INT = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFF
ONE_HUNDRED_PERCENT_BP = 10000
NO_CONDUIT = ADDRESS_ZERO
LEGACY_PROXY_CONDUIT = ADDRESS_ZERO[:-1] + "1"
