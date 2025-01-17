from typing import Literal, Optional, Sequence, Union

from pydantic import BaseModel
from web3 import Web3

from seaport.abi.ERC20 import ERC20_ABI
from seaport.abi.ERC721 import ERC721_ABI
from seaport.constants import MAX_INT
from seaport.types import (
    ApprovalAction,
    BalanceAndApproval,
    BalancesAndApprovals,
    ConsiderationItem,
    InputCriteria,
    InsufficientApproval,
    InsufficientApprovals,
    InsufficientBalance,
    InsufficientBalances,
    Item,
    OfferItem,
)
from seaport.utils.balance import balance_of
from seaport.utils.item import (
    TimeBasedItemParams,
    TokenAndIdentifierAmounts,
    get_item_index_to_criteria_map,
    get_summed_token_and_identifier_amounts,
    is_erc20_item,
    is_erc721_item,
    is_erc1155_item,
    is_native_currency_item,
)
from seaport.utils.usecase import get_transaction_methods


def approved_item_amount(owner: str, item: Item, operator: str, web3: Web3) -> int:
    if is_erc721_item(item.itemType) or is_erc1155_item(item.itemType):
        contract = web3.eth.contract(
            address=web3.toChecksumAddress(item.token), abi=ERC721_ABI
        )

        is_approved_for_all = contract.functions.isApprovedForAll(
            owner, operator
        ).call()

        return MAX_INT if is_approved_for_all else 0
    elif is_erc20_item(item.itemType):
        contract = web3.eth.contract(
            address=web3.toChecksumAddress(item.token), abi=ERC20_ABI
        )

        return contract.functions.allowance(owner, operator).call()

    # We don't need to check approvals for native tokens
    return MAX_INT


def get_approval_actions(
    *,
    insufficient_approvals: InsufficientApprovals,
    web3: Web3,
    account_address: Optional[str] = None,
) -> list[ApprovalAction]:
    from_account = account_address or web3.eth.accounts[0]

    deduped_approvals = [
        approval
        for index, approval in enumerate(insufficient_approvals)
        if index == len(insufficient_approvals) - 1
        or insufficient_approvals[index + 1].token != approval.token
    ]

    def map_insufficient_approval_to_action(
        insufficient_approval: InsufficientApproval,
    ):

        if is_erc721_item(insufficient_approval.item_type) or is_erc1155_item(
            insufficient_approval.item_type
        ):
            # setApprovalForAllCheck is the same for both ERC721 and ERC1155, defaulting to ERC721
            contract = web3.eth.contract(
                address=Web3.toChecksumAddress(insufficient_approval.token),
                abi=ERC721_ABI,
            )

            contract_fn = contract.functions.setApprovalForAll(
                insufficient_approval.operator, True
            )

        else:
            contract = web3.eth.contract(
                address=Web3.toChecksumAddress(insufficient_approval.token),
                abi=ERC20_ABI,
            )

            contract_fn = contract.functions.approve(
                insufficient_approval.operator, MAX_INT
            )

        return ApprovalAction(
            token=insufficient_approval.token,
            identifier_or_criteria=insufficient_approval.identifier_or_criteria,
            item_type=insufficient_approval.item_type,
            operator=insufficient_approval.operator,
            transaction_methods=get_transaction_methods(
                contract_fn, {"from": from_account}
            ),
        )

    return list(map(map_insufficient_approval_to_action, deduped_approvals))


def find_balance_and_approval(
    balances_and_approvals: BalancesAndApprovals,
    token: str,
    identifier_or_criteria: int,
) -> BalanceAndApproval:
    for balance_and_approval in balances_and_approvals:
        if (
            token.lower() == balance_and_approval.token.lower()
            and identifier_or_criteria == balance_and_approval.identifier_or_criteria
        ):
            return balance_and_approval

    raise ValueError("Balances and approvals didn't contain all tokens and identifiers")


def get_balances_and_approvals(
    *,
    owner: str,
    items: Sequence[Item],
    criterias: list[InputCriteria],
    operator: str,
    web3: Web3,
):
    item_index_to_criteria = get_item_index_to_criteria_map(
        items=items, criterias=criterias
    )

    def map_item_to_balances_and_approval(index_and_item: tuple[int, Item]):
        index, item = index_and_item
        approved_amount = 0

        if is_native_currency_item(item.itemType):
            # If native token, we don't need to check for approvals
            approved_amount = MAX_INT
        else:
            approved_amount = approved_item_amount(
                owner=owner,
                item=item,
                operator=operator,
                web3=web3,
            )

        return BalanceAndApproval(
            token=item.token,
            identifier_or_criteria=item_index_to_criteria[index].identifier
            if index in item_index_to_criteria
            else item.identifierOrCriteria,
            balance=balance_of(
                owner=owner,
                item=item,
                criteria=item_index_to_criteria.get(index),
                web3=web3,
            ),
            approved_amount=approved_amount,
            item_type=item.itemType,
        )

    return list(map(map_item_to_balances_and_approval, enumerate(items)))


class InsufficientBalanceAndApprovalAmounts(BaseModel):
    insufficient_balances: InsufficientBalances
    insufficient_approvals: InsufficientApprovals


def get_insufficient_balance_and_approval_amounts(
    *,
    balances_and_approvals: BalancesAndApprovals,
    token_and_identifier_amounts: TokenAndIdentifierAmounts,
    operator: str,
):
    token_and_identifier_and_amount_needed_list: list[tuple[str, int, int]] = []

    for token, identifier_to_amount in token_and_identifier_amounts.items():
        for identifier_or_criteria, amount_needed in identifier_to_amount.items():
            token_and_identifier_and_amount_needed_list.append(
                (token, identifier_or_criteria, amount_needed)
            )

    def filter_balances_or_approvals(
        filter_key: Union[
            Literal["balance"],
            Literal["approved_amount"],
        ]
    ):
        def filter_balance_or_approval(
            token_and_identifier_and_amount_needed: tuple[str, int, int]
        ):
            (
                token,
                identifier_or_criteria,
                amount_needed,
            ) = token_and_identifier_and_amount_needed

            amount: int = find_balance_and_approval(
                balances_and_approvals=balances_and_approvals,
                token=token,
                identifier_or_criteria=identifier_or_criteria,
            ).dict()[filter_key]

            return amount < amount_needed

        def map_to_balance(
            token_and_identifier_and_amount_needed: tuple[str, int, int]
        ) -> InsufficientBalance:
            (
                token,
                identifier_or_criteria,
                amount_needed,
            ) = token_and_identifier_and_amount_needed

            balance_and_approval = find_balance_and_approval(
                balances_and_approvals=balances_and_approvals,
                token=token,
                identifier_or_criteria=identifier_or_criteria,
            )

            return InsufficientBalance(
                token=token,
                identifier_or_criteria=identifier_or_criteria,
                required_amount=amount_needed,
                amount_have=balance_and_approval.dict()[filter_key],
                item_type=balance_and_approval.item_type,
            )

        return list(
            map(
                map_to_balance,
                filter(
                    filter_balance_or_approval,
                    token_and_identifier_and_amount_needed_list,
                ),
            )
        )

    def map_to_approval(insufficient_balance: InsufficientBalance):
        return InsufficientApproval(
            token=insufficient_balance.token,
            identifier_or_criteria=insufficient_balance.identifier_or_criteria,
            approved_amount=insufficient_balance.amount_have,
            required_approved_amount=insufficient_balance.required_amount,
            item_type=insufficient_balance.item_type,
            operator=operator,
        )

    (insufficient_balances, insufficient_approvals,) = (
        filter_balances_or_approvals("balance"),
        list(map(map_to_approval, filter_balances_or_approvals("approved_amount"))),
    )

    return InsufficientBalanceAndApprovalAmounts(
        insufficient_balances=insufficient_balances,
        insufficient_approvals=insufficient_approvals,
    )


# 1. The offerer should have sufficient balance of all offered items.
# 2. The offerer should have sufficient approvals set for the correct operator for all offered ERC20, ERC721, and ERC1155 items.
def validate_offer_balances_and_approvals(
    *,
    offer: list[OfferItem],
    criterias: list[InputCriteria],
    balances_and_approvals: BalancesAndApprovals,
    time_based_item_params: Optional[TimeBasedItemParams] = None,
    throw_on_insufficient_balances=True,
    throw_on_insufficient_approvals=False,
    operator: str,
):
    insufficient_balance_and_approval_amounts = (
        get_insufficient_balance_and_approval_amounts(
            balances_and_approvals=balances_and_approvals,
            token_and_identifier_amounts=get_summed_token_and_identifier_amounts(
                items=offer,
                criterias=criterias,
                time_based_item_params=time_based_item_params.copy(
                    update={"is_consideration_item": False}
                )
                if time_based_item_params
                else None,
            ),
            operator=operator,
        )
    )

    if (
        throw_on_insufficient_balances
        and insufficient_balance_and_approval_amounts.insufficient_balances
    ):
        raise ValueError(
            "The offerer does not have the amount needed to create or fulfill."
        )

    if (
        throw_on_insufficient_approvals
        and insufficient_balance_and_approval_amounts.insufficient_approvals
    ):
        raise ValueError("The offerer does not have the sufficient approvals.")

    return insufficient_balance_and_approval_amounts.insufficient_approvals


# When fulfilling a basic order, the following requirements need to be checked to ensure that the order will be fulfillable:
# 1. Offer checks need to be performed to ensure that the offerer still has sufficient balance and approvals
# 2. The fulfiller should have sufficient balance of all consideration items except for those with an
#    item type that matches the order's offered item type — by way of example, if the fulfilled order offers
#    an ERC20 item and requires an ERC721 item to the offerer and the same ERC20 item to another recipient,
#    the fulfiller needs to own the ERC721 item but does not need to own the ERC20 item as it will be sourced from the offerer.
# 3. If the fulfiller does not elect to utilize a proxy, they need to have sufficient approvals set for the
#    Seaport contract for all ERC20, ERC721, and ERC1155 consideration items on the fulfilled order except
#    for ERC20 items with an item type that matches the order's offered item type.
# 4. If the fulfiller does elect to utilize a proxy, they need to have sufficient approvals set for their
#    respective proxy contract for all ERC20, ERC721, and ERC1155 consideration items on the fulfilled order
#    except for ERC20 items with an item type that matches the order's offered item type.
# 5. If the fulfilled order specifies Ether (or other native tokens) as consideration items, the fulfiller must
#    be able to supply the sum total of those items as msg.value
def validate_basic_fulfill_balances_and_approvals(
    *,
    offer: list[OfferItem],
    consideration: list[ConsiderationItem],
    offerer_balances_and_approvals: BalancesAndApprovals,
    fulfiller_balances_and_approvals: BalancesAndApprovals,
    time_based_item_params: Optional[TimeBasedItemParams],
    offerer_operator: str,
    fulfiller_operator: str,
) -> InsufficientApprovals:
    validate_offer_balances_and_approvals(
        offer=offer,
        criterias=[],
        balances_and_approvals=offerer_balances_and_approvals,
        time_based_item_params=time_based_item_params,
        throw_on_insufficient_approvals=True,
        operator=offerer_operator,
    )

    consideration_without_offer_item_type = list(
        filter(lambda x: x.itemType != offer[0].itemType, consideration)
    )

    insufficient_balance_and_approval_amounts = (
        get_insufficient_balance_and_approval_amounts(
            balances_and_approvals=fulfiller_balances_and_approvals,
            token_and_identifier_amounts=get_summed_token_and_identifier_amounts(
                items=consideration_without_offer_item_type,
                criterias=[],
                time_based_item_params=time_based_item_params.copy(
                    update={"is_consideration_item": True}
                )
                if time_based_item_params
                else None,
            ),
            operator=fulfiller_operator,
        )
    )

    if insufficient_balance_and_approval_amounts.insufficient_balances:
        raise ValueError("The fulfiller does not have the balances needed to fulfill.")

    return insufficient_balance_and_approval_amounts.insufficient_approvals


# When fulfilling a standard order, the following requirements need to be checked to ensure that the order will be fulfillable:
# 1. Offer checks need to be performed to ensure that the offerer still has sufficient balance and approvals
# 2. The fulfiller should have sufficient balance of all consideration items after receiving all offered items
#    — by way of example, if the fulfilled order offers an ERC20 item and requires an ERC721 item to the offerer
#    and the same ERC20 item to another recipient with an amount less than or equal to the offered amount,
#    the fulfiller does not need to own the ERC20 item as it will first be received from the offerer.
# 3. If the fulfiller does not elect to utilize a proxy, they need to have sufficient approvals set for the
#    Seaport contract for all ERC20, ERC721, and ERC1155 consideration items on the fulfilled order.
# 4. If the fulfiller does elect to utilize a proxy, they need to have sufficient approvals set for their
#    respective proxy contract for all ERC20, ERC721, and ERC1155 consideration items on the fulfilled order.
# 5. If the fulfilled order specifies Ether (or other native tokens) as consideration items, the fulfiller must
#    be able to supply the sum total of those items as msg.value
def validate_standard_fulfill_balances_and_approvals(
    *,
    offer: list[OfferItem],
    consideration: list[ConsiderationItem],
    offer_criteria: list[InputCriteria],
    consideration_criteria: list[InputCriteria],
    offerer_balances_and_approvals: BalancesAndApprovals,
    fulfiller_balances_and_approvals: BalancesAndApprovals,
    time_based_item_params: Optional[TimeBasedItemParams],
    offerer_operator: str,
    fulfiller_operator: str,
) -> InsufficientApprovals:
    validate_offer_balances_and_approvals(
        offer=offer,
        criterias=offer_criteria,
        balances_and_approvals=offerer_balances_and_approvals,
        time_based_item_params=time_based_item_params,
        throw_on_insufficient_approvals=True,
        operator=offerer_operator,
    )

    summed_offer_amounts = get_summed_token_and_identifier_amounts(
        items=offer,
        criterias=offer_criteria,
        time_based_item_params=time_based_item_params.copy(
            update={"is_consideration_item": False}
        )
        if time_based_item_params
        else None,
    )

    # Deep clone existing balances
    fulfiller_balances_and_approvals_after_receiving_offered_items = list(
        map(lambda x: x.copy(), fulfiller_balances_and_approvals)
    )

    for token, identifier_or_criteria_to_amount in summed_offer_amounts.items():
        for identifier_or_criteria, amount in identifier_or_criteria_to_amount.items():
            balance_and_approval = find_balance_and_approval(
                balances_and_approvals=fulfiller_balances_and_approvals_after_receiving_offered_items,
                token=token,
                identifier_or_criteria=identifier_or_criteria,
            )

            balance_and_approval_index = (
                fulfiller_balances_and_approvals_after_receiving_offered_items.index(
                    balance_and_approval
                )
            )

            fulfiller_balances_and_approvals_after_receiving_offered_items[
                balance_and_approval_index
            ].balance += amount

    insufficient_balance_and_approval_amounts = get_insufficient_balance_and_approval_amounts(
        balances_and_approvals=fulfiller_balances_and_approvals_after_receiving_offered_items,
        token_and_identifier_amounts=get_summed_token_and_identifier_amounts(
            items=consideration,
            criterias=consideration_criteria,
            time_based_item_params=time_based_item_params.copy(
                update={"is_consideration_item": True}
            )
            if time_based_item_params
            else None,
        ),
        operator=fulfiller_operator,
    )

    if insufficient_balance_and_approval_amounts.insufficient_balances:
        raise ValueError("The fulfiller does not have the balances needed to fulfill.")

    return insufficient_balance_and_approval_amounts.insufficient_approvals
