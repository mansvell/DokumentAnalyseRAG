<script setup>
defineProps({
  role: String,
  content: String,
  time: String,
  sources: {
    type: Array,
    default: () => []
  }
})
</script>

<template>
  <div :class="role === 'user' ? 'flex justify-end animate-slide-up' : 'flex justify-start animate-slide-up'">
    <div :class="role === 'user' ? 'max-w-[82%] px-2 py-1 text-gray-800 rounded-xl bg-gray-400': 'max-w-[82%] px-2 py-1 rounded-xl bg-gray-300 text-gray-800'">
      <p class="whitespace-pre-wrap leading-relaxed">
        {{ content }}
      </p>

      <p class="mt-1 text-xs text-white">
        {{ time }}
      </p>

      <div v-if="role === 'assistant' && sources.length > 0" class="mt-3">
        <p class="mb-2 text-xs font-semibold uppercase text-gray-500">
          Quellen
        </p>

        <div class="flex flex-wrap gap-2">
          <span
            v-for="(source, index) in sources"
            :key="index"
            class="rounded-full bg-gray-200 px-3 py-1 text-xs text-gray-700"
          >
            {{ source }}
          </span>
        </div>
      </div>
    </div>
  </div>
</template>