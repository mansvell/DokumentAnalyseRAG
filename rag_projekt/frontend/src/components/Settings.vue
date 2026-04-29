<script setup>
defineProps({
  modelValue: {
    type: String,
    default: 'bg-gray-100'
  }
})

const emit = defineEmits(['update:modelValue'])

const colors = [
  { label: 'Gris clair', value: 'bg-gray-100' },
  { label: 'rouge clair', value: 'bg-red-400' },
  { label: 'Beige clair', value: 'bg-stone-100' },
  { label: 'Gris foncé', value: 'bg-gray-200' }
]
</script>

<template>
  <div class="rounded-2xl border border-gray-300 bg-white p-4 shadow-sm">
    <h2 class="mb-3 text-lg font-semibold text-gray-800">Einstellungen</h2>

  </div>
</template>