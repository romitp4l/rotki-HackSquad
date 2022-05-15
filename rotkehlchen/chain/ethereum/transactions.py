import logging
from typing import TYPE_CHECKING, List, Optional, Tuple

from rotkehlchen.chain.ethereum.constants import (
    RANGE_PREFIX_ETHINTERNALTX,
    RANGE_PREFIX_ETHTOKENTX,
    RANGE_PREFIX_ETHTX,
)
from rotkehlchen.db.ethtx import DBEthTx
from rotkehlchen.db.filtering import ETHTransactionsFilterQuery
from rotkehlchen.db.ranges import DBQueryRanges
from rotkehlchen.errors.misc import RemoteError
from rotkehlchen.logging import RotkehlchenLogsAdapter
from rotkehlchen.types import (
    ChecksumEthAddress,
    EthereumTransaction,
    EVMTxHash,
    Timestamp,
    deserialize_evm_tx_hash,
)
from rotkehlchen.utils.misc import ts_now
from rotkehlchen.utils.mixins.lockable import LockableQueryMixIn, protect_with_lock

if TYPE_CHECKING:
    from rotkehlchen.chain.ethereum.manager import EthereumManager
    from rotkehlchen.chain.ethereum.structures import EthereumTxReceipt
    from rotkehlchen.db.dbhandler import DBHandler


logger = logging.getLogger(__name__)
log = RotkehlchenLogsAdapter(logger)


class EthTransactions(LockableQueryMixIn):

    def __init__(
            self,
            ethereum: 'EthereumManager',
            database: 'DBHandler',
    ) -> None:
        super().__init__()
        self.ethereum = ethereum
        self.database = database

    def single_address_query_transactions(
            self,
            address: ChecksumEthAddress,
            start_ts: Timestamp,
            end_ts: Timestamp,
    ) -> None:
        """Only queries new transactions and adds them to the DB

        This is our attempt to identify as many transactions related to the address
        as possible. This unfortunately at the moment depends on etherscan as it's
        the only open indexing service for "appearances" of an address.

        Trueblocks ... we need you.
        """
        self._get_transactions_for_range(address=address, start_ts=start_ts, end_ts=end_ts)
        self._get_internal_transactions_for_ranges(
            address=address,
            start_ts=start_ts,
            end_ts=end_ts,
        )
        self._get_erc20_transfers_for_ranges(
            address=address,
            start_ts=start_ts,
            end_ts=end_ts,
        )

    @protect_with_lock()
    def query(
            self,
            filter_query: ETHTransactionsFilterQuery,
            has_premium: bool = False,
            only_cache: bool = False,
    ) -> Tuple[List[EthereumTransaction], int]:
        """Queries for all transactions of an ethereum address or of all addresses.

        Returns a list of all transactions filtered and sorted according to the parameters.

        May raise:
        - RemoteError if etherscan is used and there is a problem with reaching it or
        with parsing the response.
        - pysqlcipher3.dbapi2.OperationalError if the SQL query fails due to
        invalid filtering arguments.
        """
        query_addresses = filter_query.addresses

        if query_addresses is not None:
            accounts = query_addresses
        else:
            accounts = self.database.get_blockchain_accounts().eth

        if only_cache is False:
            f_from_ts = filter_query.from_ts
            f_to_ts = filter_query.to_ts
            from_ts = Timestamp(0) if f_from_ts is None else f_from_ts
            to_ts = ts_now() if f_to_ts is None else f_to_ts
            for address in accounts:
                self.single_address_query_transactions(
                    address=address,
                    start_ts=from_ts,
                    end_ts=to_ts,
                )

        dbethtx = DBEthTx(self.database)
        return dbethtx.get_ethereum_transactions_and_limit_info(
            filter_=filter_query,
            has_premium=has_premium,
        )

    def _get_transactions_for_range(
            self,
            address: ChecksumEthAddress,
            start_ts: Timestamp,
            end_ts: Timestamp,
    ) -> None:
        """Queries etherscan for all ethereum transactions of address in the given ranges.

        If any transactions are found, they are added in the DB
        """
        location_string = f'{RANGE_PREFIX_ETHTX}_{address}'
        ranges = DBQueryRanges(self.database)
        ranges_to_query = ranges.get_location_query_ranges(
            location_string=location_string,
            start_ts=start_ts,
            end_ts=end_ts,
        )
        dbethtx = DBEthTx(self.database)
        for query_start_ts, query_end_ts in ranges_to_query:
            try:
                for new_transactions in self.ethereum.etherscan.get_transactions(
                    account=address,
                    from_ts=query_start_ts,
                    to_ts=query_end_ts,
                    action='txlist',
                ):
                    # add new transactions to the DB
                    if len(new_transactions) != 0:
                        dbethtx.add_ethereum_transactions(
                            ethereum_transactions=new_transactions,
                            relevant_address=address,
                        )

                        ranges.update_used_query_range(  # update last queried time for the address
                            location_string=location_string,
                            queried_ranges=[(query_start_ts, new_transactions[-1].timestamp)],
                        )

            except RemoteError as e:
                self.ethereum.msg_aggregator.add_error(
                    f'Got error "{str(e)}" while querying ethereum transactions '
                    f'from Etherscan. Some transactions not added to the DB '
                    f'address: {address} '
                    f'from_ts: {query_start_ts} '
                    f'to_ts: {query_end_ts} ',
                )
                return

        ranges.update_used_query_range(  # entire range is now considered queried
            location_string=location_string,
            queried_ranges=[(start_ts, end_ts)],
        )

    def _get_internal_transactions_for_ranges(
            self,
            address: ChecksumEthAddress,
            start_ts: Timestamp,
            end_ts: Timestamp,
    ) -> None:
        """Queries etherscan for all internal transactions of address in the given ranges.

        If any internal transactions are found, they are added in the DB
        """
        location_string = f'{RANGE_PREFIX_ETHINTERNALTX}_{address}'
        ranges = DBQueryRanges(self.database)
        ranges_to_query = ranges.get_location_query_ranges(
            location_string=location_string,
            start_ts=start_ts,
            end_ts=end_ts,
        )
        dbethtx = DBEthTx(self.database)
        new_internal_txs = []
        for query_start_ts, query_end_ts in ranges_to_query:
            try:
                for new_internal_txs in self.ethereum.etherscan.get_transactions(
                    account=address,
                    from_ts=query_start_ts,
                    to_ts=query_end_ts,
                    action='txlistinternal',
                ):
                    if len(new_internal_txs) != 0:
                        for internal_tx in new_internal_txs:
                            # make sure all internal transaction parent transactions are in the DB
                            result = dbethtx.get_ethereum_transactions(
                                ETHTransactionsFilterQuery.make(tx_hash=internal_tx.parent_tx_hash),  # noqa: E501
                                has_premium=True,  # ignore limiting here
                            )
                            if len(result) == 0:  # parent transaction is not in the DB. Get it
                                transaction = self.ethereum.get_transaction_by_hash(internal_tx.parent_tx_hash)  # noqa: E501
                                dbethtx.add_ethereum_transactions(
                                    ethereum_transactions=[transaction],
                                    relevant_address=address,
                                )
                                timestamp = transaction.timestamp
                            else:
                                timestamp = result[0].timestamp

                            dbethtx.add_ethereum_internal_transactions(
                                transactions=[internal_tx],
                                relevant_address=address,
                            )
                            ranges.update_used_query_range(  # update last queried time for address
                                location_string=location_string,
                                queried_ranges=[(query_start_ts, timestamp)],
                            )

            except RemoteError as e:
                self.ethereum.msg_aggregator.add_error(
                    f'Got error "{str(e)}" while querying internal ethereum transactions '
                    f'from Etherscan. Transactions not added to the DB '
                    f'address: {address} '
                    f'from_ts: {query_start_ts} '
                    f'to_ts: {query_end_ts} ',
                )
                return

        ranges.update_used_query_range(  # entire range is now considered queried
            location_string=location_string,
            queried_ranges=[(start_ts, end_ts)],
        )

    def _get_erc20_transfers_for_ranges(
            self,
            address: ChecksumEthAddress,
            start_ts: Timestamp,
            end_ts: Timestamp,
    ) -> None:
        """Queries etherscan for all erc20 transfers of address in the given ranges.

        If any transfers are found, they are added in the DB
        """
        location_string = f'{RANGE_PREFIX_ETHTOKENTX}_{address}'
        dbethtx = DBEthTx(self.database)
        ranges = DBQueryRanges(self.database)
        ranges_to_query = ranges.get_location_query_ranges(
            location_string=location_string,
            start_ts=start_ts,
            end_ts=end_ts,
        )
        for query_start_ts, query_end_ts in ranges_to_query:
            try:
                for erc20_tx_hashes in self.ethereum.etherscan.get_token_transaction_hashes(
                    account=address,
                    from_ts=query_start_ts,
                    to_ts=query_end_ts,
                ):
                    for tx_hash in erc20_tx_hashes:
                        tx_hash_bytes = deserialize_evm_tx_hash(tx_hash)
                        result = dbethtx.get_ethereum_transactions(
                            ETHTransactionsFilterQuery.make(tx_hash=tx_hash_bytes),
                            has_premium=True,  # ignore limiting here
                        )
                        if len(result) == 0:  # if transaction is not there add it
                            transaction = self.ethereum.get_transaction_by_hash(tx_hash_bytes)
                            dbethtx.add_ethereum_transactions(
                                [transaction],
                                relevant_address=address,
                            )
                            timestamp = transaction.timestamp
                        else:
                            timestamp = result[0].timestamp

                        ranges.update_used_query_range(  # update last queried time for the address
                            location_string=location_string,
                            queried_ranges=[(query_start_ts, timestamp)],
                        )
            except RemoteError as e:
                self.ethereum.msg_aggregator.add_error(
                    f'Got error "{str(e)}" while querying token transactions'
                    f'from Etherscan. Transactions not added to the DB '
                    f'address: {address} '
                    f'from_ts: {query_start_ts} '
                    f'to_ts: {query_end_ts} ',
                )

        ranges.update_used_query_range(  # entire range is now considered queried
            location_string=location_string,
            queried_ranges=[(start_ts, end_ts)],
        )

    def get_or_query_transaction_receipt(
            self,
            tx_hash: EVMTxHash,
    ) -> 'EthereumTxReceipt':
        """
        Gets the receipt from the DB if it exists. If not queries the chain for it,
        saves it in the DB and then returns it.

        Also if the actual transaction does not exist in the DB it queries it and saves it there.

        May raise:

        - DeserializationError
        - RemoteError if the transaction hash can't be found in any of the connected nodes
        """
        dbethtx = DBEthTx(self.database)
        with self.ethereum.receipts_query_lock:
            # If the transaction is not in the DB then query it and add it
            result = dbethtx.get_ethereum_transactions(
                filter_=ETHTransactionsFilterQuery.make(tx_hash=tx_hash),
                has_premium=True,  # we don't need any limiting here
            )
            if len(result) == 0:
                transaction = self.ethereum.get_transaction_by_hash(tx_hash)
                dbethtx.add_ethereum_transactions([transaction], relevant_address=None)
                self._get_internal_transactions_for_ranges(
                    address=transaction.from_address,
                    start_ts=transaction.timestamp,
                    end_ts=transaction.timestamp,
                )
                self._get_erc20_transfers_for_ranges(
                    address=transaction.from_address,
                    start_ts=transaction.timestamp,
                    end_ts=transaction.timestamp,
                )

            tx_receipt = dbethtx.get_receipt(tx_hash)
            if tx_receipt is not None:
                return tx_receipt

            # not in the DB, so we need to query the chain for it
            tx_receipt_data = self.ethereum.get_transaction_receipt(tx_hash=tx_hash)
            dbethtx.add_receipt_data(tx_receipt_data)
            tx_receipt = dbethtx.get_receipt(tx_hash)
            return tx_receipt  # type: ignore  # tx_receipt was just added in the DB so should be there  # noqa: E501

    def get_receipts_for_transactions_missing_them(self, limit: Optional[int] = None) -> None:
        """
        Searches the database for up to `limit` transactions that have no corresponding receipt
        and for each one of them queries the receipt and saves it in the DB.

        It's protected by a lock to not enter the same code twice
        (i.e. from periodic tasks and from pnl report history events gathering)
        """
        with self.ethereum.receipts_query_lock:
            dbethtx = DBEthTx(self.database)
            hash_results = dbethtx.get_transaction_hashes_no_receipt(
                tx_filter_query=None,
                limit=limit,
            )

            if len(hash_results) == 0:
                return  # nothing to do

            for entry in hash_results:
                tx_receipt_data = self.ethereum.get_transaction_receipt(tx_hash=entry)
                dbethtx.add_receipt_data(tx_receipt_data)
