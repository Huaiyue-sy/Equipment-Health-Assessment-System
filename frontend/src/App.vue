<template>
  <div id="app-shell">
    <nav v-if="isLoggedIn" class="topbar">
      <div class="topbar-left">
        <router-link to="/dashboard" class="brand">iHealthSim</router-link>
        <router-link to="/diagnosis" class="nav-link">诊断报告</router-link>
        <router-link v-if="userRole === 'admin'" to="/admin" class="nav-link">权限管理</router-link>
      </div>
      <div class="topbar-right">
        <span class="user-tag">{{ username }} <span class="role-dot" :class="'dot-' + userRole"></span></span>
        <button class="btn-ghost" @click="logout">退出</button>
      </div>
    </nav>
    <main :class="{ 'has-topbar': isLoggedIn }">
      <router-view @logged-in="onLogin" />
    </main>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import { useRouter } from 'vue-router'

const router = useRouter()
const token = ref(localStorage.getItem('token') || '')
const username = ref(localStorage.getItem('username') || '')
const userRole = ref(localStorage.getItem('userRole') || '')

const isLoggedIn = computed(() => !!token.value)

function onLogin({ token: t, username: u, role: r }) {
  token.value = t
  username.value = u
  userRole.value = r || 'operator'
  localStorage.setItem('token', t)
  localStorage.setItem('username', u)
  localStorage.setItem('userRole', r || 'operator')
  router.push('/dashboard')
}

function logout() {
  token.value = ''
  username.value = ''
  userRole.value = ''
  localStorage.removeItem('token')
  localStorage.removeItem('username')
  localStorage.removeItem('userRole')
  router.push('/login')
}
</script>

<style scoped>
#app-shell {
  min-height: 100vh;
  background: #f8f9fb;
}

.topbar {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  height: 52px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 24px;
  background: #fff;
  border-bottom: 1px solid #e8ecf1;
  z-index: 100;
}

.topbar-left {
  display: flex;
  align-items: center;
  gap: 24px;
}

.brand {
  font-size: 18px;
  font-weight: 700;
  color: #1a73e8;
  text-decoration: none;
  letter-spacing: -0.3px;
}

.nav-link {
  font-size: 13px;
  color: #4e5969;
  text-decoration: none;
  padding: 4px 0;
  border-bottom: 2px solid transparent;
  transition: all 0.2s;
}

.nav-link:hover {
  color: #1a73e8;
}

.topbar-right {
  display: flex;
  align-items: center;
  gap: 16px;
}

.user-tag {
  font-size: 13px;
  color: #5f6b7a;
}

.btn-ghost {
  background: none;
  border: 1px solid #dde2e8;
  border-radius: 6px;
  padding: 4px 14px;
  font-size: 13px;
  color: #5f6b7a;
  cursor: pointer;
  transition: all 0.15s;
}

.btn-ghost:hover {
  border-color: #c0c8d4;
  color: #2c3e50;
}

.role-dot {
  display: inline-block;
  width: 6px;
  height: 6px;
  border-radius: 50%;
  margin-left: 2px;
  vertical-align: middle;
}

.dot-admin    { background: #1a73e8; }
.dot-operator { background: #86909c; }

.has-topbar {
  padding-top: 52px;
}
</style>
