<script setup>
import { ref , nextTick} from 'vue'

const props = defineProps({ //ermöglicht chatInput diese Werte von App.vue(parent) zu empfangen (input soll gesperrt werden?Datei schon ausgewählt?
  disabled: Boolean,
  uploadedFiles: {
    type: Array,
    default: () => []
  }
})
const emit  =defineEmits(['ask', 'files-selected']) //ChatInput verwendet emit ,um event (ask und fil-se) an App.vue zu senden

const question= ref('')// ou le msg est gespeichert
const textareaRef= ref(null)

function submitQuestion() {   //submitQuestion braucht keinen Parameter denn emit('ask', value) schickt und handleAsk(question) empfängt
  const value= question.value.trim()  //entferne Leerzeichen
  if (!value || props.disabled) return

  emit('ask', value)  //
  question.value = ''

  nextTick(() => { //nach der Bildschirmaktualisierung passt die Feldgröße an
    autoResize()
  })
}

function handleFileChange(event) {
  const files = Array.from(event.target.files || [])//ruft die ausgewählten Dateien ab und Arry.from Wandelt diese FileList in JavaScript-Array um
  if (!files.length) return

  emit('files-selected', [...props.uploadedFiles, ...files])//sende die File an App.vue
  event.target.value = ''
}

function autoResize() { //passt die Feldgröße an
  const el = textareaRef.value
  if (!el) return
  el.style.height = 'auto'
  el.style.height = Math.min(el.scrollHeight, 140) + 'px'
}
</script>

<template>

    <div v-if="uploadedFiles.length > 0" class="mb-2 flex flex-wrap gap-2">
      <div v-for="(file, i) in uploadedFiles" :key="i"
        class="flex items-center gap-2 rounded-xl bg-red-500 px-2 py-1 text-xs text-white" >
        📄 <span class="truncate max-w-[120px]">{{ file.name }}</span>
      </div>
    </div>

  <div class="rounded-2xl border-t-2 border-red-300 bg-white p-3">
    <div class="flex flex-row gap-2 sm:flex-row">
      <textarea
          ref="textareaRef"
          v-model="question"
          rows="1"
          class="flex-1 resize-none overflow-y-auto px-2 py-2 outline-none text-sm leading-6 max-h-[140px] min-h-[44px]"
          placeholder="Frage stellen..."
          @input="autoResize"
          @keydown.enter.exact.prevent="submitQuestion"
      />

    <div class="mt-2 flex items-center justify-between gap-2">
        <label class="flex items-center justify-center rounded-xl bg-gray-200 px-3 py-2 text-sm hover:bg-red-500 cursor-pointer">
          ➕ PDF
          <input type="file" multiple accept=".pdf" class="hidden" @change="handleFileChange" />
        </label>


        <button class="flex items-center justify-center rounded-xl bg-green-400 px-4 py-2 text-sm
        text-white disabled:opacity-50" :disabled="disabled" @click="submitQuestion">
          Senden
        </button>
    </div>

    </div>
  </div>
</template>