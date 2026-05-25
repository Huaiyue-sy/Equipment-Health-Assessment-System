<template>
  <div class="auth-page">
    <div class="auth-card">
      <h1 class="auth-title">创建账号</h1>
      <p class="auth-sub">注册后即可访问设备健康看板</p>

      <form @submit.prevent="submit" class="auth-form">
        <label class="field">
          <span>用户名</span>
          <input v-model="form.username" type="text" placeholder="2-64 个字符" autocomplete="username" />
        </label>
        <label class="field">
          <span>邮箱</span>
          <input v-model="form.email" type="email" placeholder="your@email.com" autocomplete="email" />
        </label>
        <label class="field">
          <span>密码</span>
          <input v-model="form.password" type="password" placeholder="至少 6 位" autocomplete="new-password" />
        </label>

        <p v-if="error" class="error">{{ error }}</p>
        <p v-if="ok" class="ok">{{ ok }}</p>

        <button type="submit" class="btn-primary" :disabled="loading">
          {{ loading ? '注册中…' : '注册' }}
        </button>
      </form>

      <p class="auth-foot">
        已有账号？<router-link to="/login">返回登录</router-link>
      </p>
    </div>
  </div>
</template>

<script setup>
import { reactive, ref } from 'vue'
import { apiRegister } from '../api'

const form = reactive({ username: '', email: '', password: '' })
const loading = ref(false)
const error = ref('')
const ok = ref('')

async function submit() {
  error.value = ''
  ok.value = ''
  if (!form.username.trim() || !form.email.trim() || !form.password) {
    error.value = '请填写所有字段'
    return
  }
  loading.value = true
  try {
    await apiRegister(form.username.trim(), form.email.trim(), form.password)
    ok.value = '注册成功，即将跳转登录页…'
    setTimeout(() => {
      window.location.href = '/#/login'
    }, 1200)
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

.ok {
  color: #099268;
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
