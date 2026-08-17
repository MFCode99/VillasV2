<script setup>
import { onMounted, reactive, ref } from 'vue'
import { api, errorMessage } from '../services/api'
import { useFeedbackStore } from '../stores/feedback'
const feedback=useFeedbackStore();const categories=ref([]);const dialog=ref(false);const form=reactive({slug:'',label:'',sort_order:0,active:true});const editing=ref(false)
async function load(){try{categories.value=(await api.get('/admin/catalog')).data.categories}catch(e){feedback.show(errorMessage(e),'error')}}
function open(item=null){editing.value=Boolean(item);Object.assign(form,item?{slug:item.slug,label:item.label,sort_order:item.sortOrder,active:item.active}:{slug:'',label:'',sort_order:categories.value.length,active:true});dialog.value=true}
async function save(){try{await api.post('/admin/categories',form);dialog.value=false;await load();feedback.show('Categoria guardada.')}catch(e){feedback.show(errorMessage(e),'error')}}
async function toggle(item){try{await api.post('/admin/categories',{slug:item.slug,label:item.label,sort_order:item.sortOrder,active:!item.active});await load();feedback.show('Categoria atualizada.')}catch(e){feedback.show(errorMessage(e),'error')}}
onMounted(load)
</script>
<template><div class="page"><div class="page-head"><div><h1>Categorias</h1><p>Organize a navegação e a visibilidade do catálogo.</p></div><v-btn color="primary" prepend-icon="mdi-plus" @click="open()">Nova categoria</v-btn></div><v-row><v-col v-for="item in categories" :key="item.slug" cols="12" md="6" lg="4"><v-card class="soft-card pa-5"><div class="d-flex justify-space-between align-start"><div><div class="text-h6 font-weight-bold">{{ item.label }}</div><div class="text-caption text-medium-emphasis">{{ item.slug }} · ordem {{ item.sortOrder }}</div></div><v-switch :model-value="item.active" hide-details color="success" @update:model-value="toggle(item)" /></div><v-btn block variant="tonal" class="mt-5" prepend-icon="mdi-pencil-outline" @click="open(item)">Editar</v-btn></v-card></v-col></v-row>
  <v-dialog v-model="dialog" max-width="540"><v-card><v-card-title class="pa-6 pb-2">{{editing?'Editar categoria':'Nova categoria'}}</v-card-title><v-card-text class="pa-6"><v-text-field v-model="form.slug" label="Código" :disabled="editing"/><v-text-field v-model="form.label" label="Nome"/><v-text-field v-model.number="form.sort_order" type="number" label="Ordem"/><v-switch v-model="form.active" color="success" label="Categoria ativa"/></v-card-text><v-card-actions class="px-6 pb-6"><v-spacer/><v-btn variant="text" @click="dialog=false">Cancelar</v-btn><v-btn color="primary" @click="save">Guardar</v-btn></v-card-actions></v-card></v-dialog>
</div></template>
