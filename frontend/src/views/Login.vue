<template>
  <div class="auth-page">
    <div class="auth-card">
      <h1 class="auth-title">iHealthSim</h1>
      <p class="auth-sub">设备健康评估系统</p>

      <form @submit.prevent="submit" class="auth-form">
        <label class="field">
          <span>用户名</span>
          <input v-model="form.username" type="text" placeholder="请输入用户名" autocomplete="username" />
        </label>
        <label class="field">
          <span>密码</span>
          <input v-model="form.password" type="password" placeholder="请输入密码" autocomplete="current-password" />
        </label>

        <p v-if="error" class="error">{{ error }}</p>

        <button type="submit" class="btn-primary" :disabled="loading">
          {{ loading ? '登录中…' : '登录' }}
        </button>
      </form>

      <p class="auth-foot">
        没有账号？<router-link to="/register">立即注册</router-link>
      </p>
    </div>
  </div>
</template>

<script setup>
import { reactive, ref } from 'vue'
import { apiLogin } from '../api'

const emit = defineEmits(['logged-in'])
const form = reactive({ username: '', password: '' })
const loading = ref(false)
const error = ref('')

async function submit() {
  error.value = ''
  if (!form.username.trim() || !form.password) {
    error.value = '请填写用户名和密码'
    return
  }
  loading.value = true
  try {
    const res = await apiLogin(form.username.trim(), form.password)
    emit('logged-in', { token: res.token, username: res.user.username, role: res.user.role })
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.auth-page {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 24px;
}

.auth-card {
  width: 100%;
  max-width: 400px;
  background: #fff;
  border-radius: 12px;
  padding: 40px 36px;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.06), 0 4px 16px rgba(0, 0, 0, 0.04);
}

.auth-title {
  font-size: 26px;
  font-weight: 700;
  color: #1a73e8;
  text-align: center;
  letter-spacing: -0.5px;
}

.auth-sub {
  text-align: center;
  color: #86909c;
  font-size: 14px;
  margin-top: 4px;
  margin-bottom: 32px;
}

.auth-form {
  display: flex;
  flex-direction: column;
  gap: 18px;
}

.field {
  display: flex;
  flex-direction: column;
  gap: 6px;
  font-size: 13px;
  color: #4e5969;
}

.field input {
  height: 42px;
  border: 1px solid #e5e8eb;
  border-radius: 8px;
  padding: 0 12px;
  font-size: 14px;
  outline: none;
  transition: border-color 0.15s;
}

.field input:focus {
  border-color: #1a73e8;
  box-shadow: 0 0 0 2px rgba(26, 115, 232, 0.1);
}

.btn-primary {
  height: 44px;
  background: #1a73e8;
  color: #fff;
  border: none;
  border-radius: 8px;
  font-size: 15px;
  font-weight: 600;
  cursor: pointer;
  transition: background 0.15s;
  margin-top: 4px;
}

.btn-primary:hover {
  background: #1557b0;
}

.btn-primary:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.error {
  color: #e03131;
  font-size: 13px;
  text-align: center;
  margin: 0;
}

.auth-foot {
  text-align: center;
  font-size: 13px;
  color: #86909c;
  margin-top: 24px;
  margin-bottom: 0;
}

.auth-foot a {
  color: #1a73e8;
  text-decoration: none;
  font-weight: 500;
}
</style>
