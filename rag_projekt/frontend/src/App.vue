<script setup>
import { computed, ref } from 'vue'
import AppHeader from './components/AppHeader.vue'
import ChatInput from './components/ChatInput.vue'
import ChatMessage from './components/ChatMessage.vue'
import HistoryPanel from './components/HistoryPanel.vue'
import SettingsPanel from './components/Settings.vue'

function getCurrentTime() {
  const  now=new Date()
  return now.toLocaleTimeString( [], { hour: '2-digit', minute: '2-digit' })
}

function createNewChat(id = Date.now()) {
  return {
    id,
    title: 'Neuer Chat',
    uploadedFiles: [],
    messages: [
      {
        role: 'assistant',
        content: 'Hallo! Wie kann ich Ihnen helfen?',
        time: getCurrentTime(),
        sources: []
      }
    ]
  }
}

const chats = ref([createNewChat(1)])
const activeChatId = ref(1)
const isLoading = ref(false)
const sidebarOpen = ref(true)
const showSettings = ref(false)
const backgroundClass = ref('bg-gray-100')

const activeChat = computed(() =>
  chats.value.find(chat => chat.id === activeChatId.value)
)

function updateChatTitle(chat, question) {
  if ( chat.title === 'Neuer Chat') {
    chat.title = question.slice(0, 28)
  }
}

async function handleAsk(question) {
  if (!activeChat.value || !question.trim()) return

  activeChat.value.messages.push({ //man erstellt und zeigt die Nachricht von User im Chat
    role: 'user',
    content: question,
    time: getCurrentTime(),
    sources: []
  })

  updateChatTitle(activeChat.value, question)
  isLoading.value = true

  try {
    const response  =await fetch ('http://127.0.0.1:8000/query', {
      method : 'POST',
      headers: {
        'Content-Type': 'application/json'
      }  ,
      body: JSON.stringify ({
        query : question    //Umwandlung der Frage in JSON
      })
    })

    const data  = await response.json() //recupere le Antwort des Backends (query, answer, source)

    activeChat.value.messages.push({//Antwort des Agenten wird im Chat gezeigt
      role: 'assistant',
      content: data.answer,
      time: getCurrentTime(),
      sources: data.sources || []
    })
  } catch (error) {
    activeChat.value.messages.push({
      role: 'assistant',
      content: 'Fehler bei der Verbindung mit dem Backend.',
      time: getCurrentTime(),
      sources: []
    })
    console.error(error)
  } finally {
    isLoading.value = false
  }
}

function selectChat(chatId) {
  activeChatId.value = chatId
}
function handleFilesSelected(files) {
  if (!activeChat.value) return
  activeChat.value.uploadedFiles = files
}

function newChat() {
  const chat = createNewChat()
  chats.value.unshift(chat)
  activeChatId.value = chat.id
}


</script>

<template>
  <div :class="['min-h-screen text-gray-800', backgroundClass]">
    <AppHeader />

    <div class="flex h-[calc(100vh-64px)]">

      <aside v-if="sidebarOpen" class="w-50  bg-gray-50" >
        <HistoryPanel :chats="chats" :active-chat-id="activeChatId" @select-chat="selectChat" @new-chat="newChat" />
      </aside>

      <div class="flex min-w-0 flex-1 ">
         <div class="flex min-w-0 flex-1 flex-col">
            <div class="flex items-center justify-between border-b border-gray-300 bg-white/80 px-4 py-3 backdrop-blur">

               <div class ="flex gap-2 items-center">
                 <button class="rounded-xl border border-gray-300 bg-white px-3 py-2 text-sm text-gray-700 hover:bg-gray-100"
                  @click="sidebarOpen = !sidebarOpen" >    ☰
                </button>
               </div>

               <div class ="flex gap-2 items-center">
                 <button class="rounded-xl border border-gray-300 bg-white px-3 py-2 text-sm text-gray-700  hover:bg-gray-100"
                  @click="showSettings = !showSettings"  >    Einstellungen
                </button>
               </div>
            </div>

            <!-- Nachricht-->
            <div class="flex-1 overflow-y-auto px-6 py-6">
              <div class="mx-auto flex w-full max-w-4xl flex-col gap-5">
                <ChatMessage
                  v-for="(message, index) in activeChat?.messages || []"
                  :key="index"
                  :role="message.role"
                  :content="message.content"
                  :time="message.time"
                  :sources="message.sources"
                />

                <div v-if="isLoading" class="flex justify-start animate-fade-in">
                  <div class="px-2 py-1">
                    <div class="flex items-center gap-3">
                      <div class="flex gap-1">
                        <span class="h-2.5 w-2.5 animate-bounce rounded-full bg-gray-500 [animation-delay:0ms]"></span>
                        <span class="h-2.5 w-2.5 animate-bounce rounded-full bg-gray-500 [animation-delay:150ms]"></span>
                        <span class="h-2.5 w-2.5 animate-bounce rounded-full bg-gray-500 [animation-delay:300ms]"></span>
                      </div>
                      <span class="text-sm text-gray-500">Think-ai denkt nach...</span>
                    </div>
                  </div>
                </div>

              </div>
            </div>

            <div class="sticky bottom-0 border-t border-gray-300 bg-gray-400 px-4 py-4 backdrop-blur">
              <div class="mx-auto max-w-4xl">
                <ChatInput
                  :disabled="isLoading"
                  :uploaded-files="activeChat?.uploadedFiles || []"
                  @ask="handleAsk"
                  @files-selected="handleFilesSelected"
                />
              </div>
            </div>
         </div>

         <aside v-if="showSettings" class="w-50 rounded-2xl border-l border-gray-300 bg-gray-50 p-4" >
           <SettingsPanel v-model="backgroundClass" />
         </aside>
      </div>
    </div>
  </div>
</template>