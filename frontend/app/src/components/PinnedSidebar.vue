<script setup lang="ts">
import { type ComputedRef } from 'vue';

defineProps<{ visible: boolean }>();

const emit = defineEmits<{ (e: 'visible:update', visible: boolean): void }>();

const ReportActionableCard = defineAsyncComponent(
  () => import('@/components/profitloss/ReportActionableCard.vue')
);

const visibleUpdate = (visible: boolean) => {
  emit('visible:update', visible);
};

const { pinned } = storeToRefs(useAreaVisibilityStore());

const component: ComputedRef = computed(() => {
  const pinnedValue = get(pinned);
  if (pinnedValue && pinnedValue.name === 'report-actionable-card') {
    return ReportActionableCard;
  }
  return null;
});
</script>

<template>
  <VNavigationDrawer
    class="pinned-sidebar"
    clipped
    width="520px"
    :value="visible"
    right
    temporary
    hide-overlay
    @input="visibleUpdate($event)"
  >
    <div>
      <Component
        :is="component"
        v-if="pinned && component"
        v-bind="pinned.props"
      />
    </div>
  </VNavigationDrawer>
</template>

<style scoped lang="scss">
.pinned-sidebar {
  top: 64px !important;
  box-shadow: 0 2px 12px rgba(74, 91, 120, 0.1);
  padding-top: 0 !important;
  border-top: var(--v-rotki-light-grey-darken1) solid thin;

  &--mobile {
    top: 56px !important;
  }

  &.v-navigation-drawer {
    &--is-mobile {
      padding-top: 0 !important;
    }
  }
}
</style>
