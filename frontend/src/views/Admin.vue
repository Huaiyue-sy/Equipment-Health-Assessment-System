<template>
  <div class="admin-page" v-cloak>
    <h2 class="page-title">用户权限管理</h2>

    <div v-if="error" class="err-msg">{{ error }}</div>

    <div class="user-table-wrap">
      <table class="user-table">
        <thead>
          <tr>
            <th>ID</th>
            <th>用户名</th>
            <th>角色</th>
            <th>设备权限</th>
            <th>设置</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="u in users" :key="u.id">
            <td>{{ u.id }}</td>
            <td><strong>{{ u.username }}</strong></td>
            <td><span class="role-tag" :class="'role-' + u.role">{{ u.role }}</span></td>
            <td>
              <span v-if="u.devices.includes('*')" class="perm-all">全部设备</span>
              <span v-else class="perm-devices">{{ u.devices.join(', ') || '无权限' }}</span>
            </td>
            <td>
              <button class="btn-set" @click="openEdit(u)">设置权限</button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- 编辑弹窗 -->
    <div v-if="editing" class="modal-mask" @click.self="editing = null">
      <div class="modal-box">
        <h3>设置 {{ editing.username }} 的设备权限</h3>
        <div class="check-list">
          <label class="check-item">
            <input type="checkbox" v-model="permAll" @change="onPermAllChange" />
            <span>全部设备（管理员权限）</span>
          </label>
          <label class="check-item" v-for="d in deviceList" :key="d">
            <input type="checkbox" :value="d" v-model="permDevices" :disabled="permAll" />
            <span>{{ d }}</span>
          </label>
        </div>
        <div class="modal-actions">
          <button class="btn-cancel" @click="editing = null">取消</button>
          <button class="btn-save" :disabled="saving" @click="savePerms">{{ saving ? '保存中...' : '保存' }}</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { apiAdminUsers, apiAdminSetUserDevices, apiMe } from '../api'

const router = useRouter()
const users = ref([])
const error = ref('')
const editing = ref(null)
const permAll = ref(false)
const permDevices = ref([])
const saving = ref(false)
const deviceList = ['PUMP-001', 'PUMP-002', 'PUMP-003', 'PUMP-004', 'PUMP-005']

onMounted(async () => {
  try {
    const me = await apiMe()
    if (me.user?.role !== 'admin') {
      router.replace('/dashboard')
      return
    }
  } catch {
    router.replace('/dashboard')
    return
  }

  try {
    const res = await apiAdminUsers()
    if (res.ok) users.value = res.users
  } catch {
    error.value = '加载用户列表失败'
  }
})

function openEdit(user) {
  editing.value = user
  permAll.value = user.devices.includes('*')
  permDevices.value = permAll.value ? [] : [...user.devices]
}

function onPermAllChange() {
  if (permAll.value) permDevices.value = []
}

async function savePerms() {
  if (!editing.value) return
  saving.value = true
  try {
    const devices = permAll.value ? ['*'] : [...permDevices.value]
    const res = await apiAdminSetUserDevices(editing.value.id, devices)
    if (res.ok) {
      editing.value.devices = devices
      editing.value = null
    }
  } catch {
    error.value = '保存失败'
  } finally {
    saving.value = false
  }
}
</script>

<style scoped>
.admin-page {
  max-width: 900px;
  margin: 0 auto;
  padding: 24px;
}

.page-title {
  font-size: 20px;
  font-weight: 700;
  color: #1d2129;
  margin: 0 0 20px;
}

.err-msg {
  padding: 10px 14px;
  background: #fee2e2;
  color: #b91c1c;
  border-radius: 8px;
  margin-bottom: 16px;
  font-size: 13px;
}

.user-table-wrap {
  background: #fff;
  border: 1px solid #e8ecf1;
  border-radius: 10px;
  overflow: hidden;
}

.user-table {
  width: 100%;
  border-collapse: collapse;
}

.user-table th {
  font-size: 12px;
  font-weight: 500;
  color: #86909c;
  text-align: left;
  padding: 10px 16px;
  border-bottom: 1px solid #f2f3f5;
  background: #fafbfc;
}

.user-table td {
  font-size: 13px;
  padding: 12px 16px;
  border-bottom: 1px solid #fafbfc;
  color: #4e5969;
}

.role-tag {
  font-size: 11px;
  font-weight: 600;
  padding: 2px 10px;
  border-radius: 999px;
}

.role-admin {
  background: #dbeafe;
  color: #1d4ed8;
}

.role-operator {
  background: #f2f3f5;
  color: #4e5969;
}

.perm-all {
  color: #1a73e8;
  font-weight: 600;
  font-size: 12px;
}

.perm-devices {
  font-size: 12px;
  color: #4e5969;
}

.btn-set {
  padding: 4px 12px;
  font-size: 12px;
  font-weight: 500;
  border: 1px solid #dde2e8;
  border-radius: 6px;
  background: #fff;
  color: #4e5969;
  cursor: pointer;
  transition: all 0.2s;
}

.btn-set:hover {
  border-color: #1a73e8;
  color: #1a73e8;
  background: #f0f6ff;
}

/* modal */
.modal-mask {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.3);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 100;
}

.modal-box {
  background: #fff;
  border-radius: 12px;
  padding: 24px;
  width: 400px;
  max-height: 80vh;
  overflow-y: auto;
  box-shadow: 0 8px 30px rgba(0, 0, 0, 0.12);
}

.modal-box h3 {
  font-size: 16px;
  font-weight: 600;
  margin: 0 0 18px;
  color: #1d2129;
}

.check-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
  margin-bottom: 20px;
}

.check-item {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  color: #4e5969;
  cursor: pointer;
}

.check-item input[type="checkbox"] {
  width: 16px;
  height: 16px;
  accent-color: #1a73e8;
  cursor: pointer;
}

.check-item input:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.modal-actions {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
}

.btn-cancel {
  padding: 8px 18px;
  font-size: 13px;
  border: 1px solid #dde2e8;
  border-radius: 6px;
  background: #fff;
  color: #4e5969;
  cursor: pointer;
}

.btn-save {
  padding: 8px 18px;
  font-size: 13px;
  font-weight: 600;
  border: none;
  border-radius: 6px;
  background: #1a73e8;
  color: #fff;
  cursor: pointer;
  transition: background 0.2s;
}

.btn-save:hover {
  background: #1557b0;
}

.btn-save:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
</style>
