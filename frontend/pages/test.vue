<template>
  <div class="test-page">
    <h1>Test Page</h1>
    <p>If you see this, Vue is working!</p>
    <button @click="count++">Count: {{ count }}</button>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue';
const count = ref(0);
</script>