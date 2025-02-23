<script setup lang="ts">
import { AddressNamePriority } from '@/types/settings/address-name-priorities';
import { PriceOracle } from '@/types/settings/price-oracle';
import { type PrioritizedListItemData } from '@/types/settings/prioritized-list-data';
import { type PrioritizedListId } from '@/types/settings/prioritized-list-id';
import { toSentenceCase } from '@/utils/text';

const props = defineProps<{
  data: PrioritizedListItemData<PrioritizedListId>;
}>();

const { data } = toRefs(props);

const size = computed<string>(() => {
  const defaultSize = '48px';
  if (get(data).extraDisplaySize) {
    return get(data).extraDisplaySize ?? defaultSize;
  }
  return defaultSize;
});

const { t } = useI18n();

const labels: { [keys in PrioritizedListId]: string } = {
  [PriceOracle.UNISWAP2]: t('oracles.uniswap_v2').toString(),
  [PriceOracle.UNISWAP3]: t('oracles.uniswap_v3').toString(),
  [PriceOracle.MANUALCURRENT]: t('oracles.manual_latest').toString(),
  [AddressNamePriority.BLOCKCHAIN_ACCOUNT]: t(
    'address_book.hint.priority.list.blockchain_account_labels'
  ).toString(),
  [AddressNamePriority.ENS_NAMES]: t(
    'address_book.hint.priority.list.ens_names'
  ).toString(),
  [AddressNamePriority.ETHEREUM_TOKENS]: t(
    'address_book.hint.priority.list.ethereum_tokens'
  ).toString(),
  [AddressNamePriority.GLOBAL_ADDRESSBOOK]: t(
    'address_book.hint.priority.list.global_address_book'
  ).toString(),
  [AddressNamePriority.HARDCODED_MAPPINGS]: t(
    'address_book.hint.priority.list.hardcoded_mappings'
  ).toString(),
  [AddressNamePriority.PRIVATE_ADDRESSBOOK]: t(
    'address_book.hint.priority.list.private_address_book'
  ).toString(),
  blockchain: '',
  coingecko: '',
  cryptocompare: '',
  fiat: '',
  manual: '',
  defillama: '',
  empty_list_id: ''
};
</script>

<template>
  <VRow align="center">
    <VCol v-if="data.icon" cols="auto">
      <AdaptiveWrapper>
        <VImg
          :width="size"
          contain
          position="left"
          :max-height="size"
          :src="data.icon"
        />
      </AdaptiveWrapper>
    </VCol>
    <VCol v-if="labels[data.identifier]" cols="auto">
      {{ labels[data.identifier] }}
    </VCol>
    <VCol v-else cols="auto">
      {{ toSentenceCase(data.identifier) }}
    </VCol>
  </VRow>
</template>
