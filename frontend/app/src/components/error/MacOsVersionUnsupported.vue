<script setup lang="ts">
const { t } = useI18n();
const { closeApp } = useInterop();
</script>

<template>
  <ErrorScreen
    class="macos-unsupported"
    :header="t('macos_unsupported.header')"
    :alternative="t('macos_unsupported.message')"
  >
    <VBtn depressed color="primary" @click="closeApp()">
      {{ t('common.actions.terminate') }}
    </VBtn>
  </ErrorScreen>
</template>

<style scoped lang="scss">
.macos-unsupported {
  padding: 2rem 0;
  background-color: white;
}
</style>
