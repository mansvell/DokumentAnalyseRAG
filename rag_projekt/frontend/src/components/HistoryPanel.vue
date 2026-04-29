<script setup>
defineProps({
  chats: {
    type: Array,
    default: () => []
  },
  activeChatId: {
    type: Number,
    default: null
  }
})

const emit = defineEmits(['select-chat', 'new-chat'])
</script>

<template>
  <div class="flex h-full flex-col bg-gray-400   bg-gray-50">

      <p class ="text-xl font-bold text-center"> °Verlauf</p>

    <div class="border-b border-gray-300 p-4">
      <button
        class="w-full rounded-xl bg-green-400 px-4 py-2 font-semibold text-white transition hover:bg-gray-700"
        @click="emit('new-chat')" >
        + Neuer Chat
      </button>
    </div>

    <div class="flex-1 overflow-y-auto p-3">
      <button
        v-for="chat in chats"
        :key="chat.id"
        class="mb-2 w-full rounded-xl px-3 py-3 text-left text-sm transition"
        :class="chat.id === activeChatId ? 'bg-gray-800 text-gray-300' : 'bg-gray-300 text-gray-900'"
        @click="emit('select-chat', chat.id)"
      >
        <p class="truncate font-medium">{{ chat.title }}</p>
      </button>
    </div>
  </div>
</template>