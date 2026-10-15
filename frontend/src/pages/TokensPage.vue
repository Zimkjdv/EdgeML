<script setup lang="ts">
import { Download, QuestionFilled, UploadFilled } from '@element-plus/icons-vue'
import { locale, t } from '../i18n'
import { injectWorkspace } from '../workspaceContext'
import type { Dataset, TrainedModel } from '../workspaceTypes'

const {
  apiTokens, newApiToken, apiTokenForm, apiTokenLoading, formatDate, api, createApiToken, copyApiToken, revokeApiToken
} = injectWorkspace()
</script>

<template>
<section class="tokens-page">
      <el-card class="workspace token-workspace" v-loading="apiTokenLoading">
        <template #header><div class="result-heading"><span>{{ t('apiTokenManagement') }}</span><el-tag type="info" effect="light">{{ apiTokens.length }} {{ t('apiTokens') }}</el-tag></div></template>
        <p class="registry-intro">{{ t('apiTokenHint') }}</p>
        <el-alert v-if="newApiToken" type="success" :closable="false" class="token-created-alert">
          <template #title>{{ t('tokenShownOnce') }}</template>
          <div class="token-value-row"><code>{{ newApiToken }}</code><el-button size="small" type="primary" plain @click="copyApiToken">{{ t('copyToken') }}</el-button></div>
        </el-alert>
        <el-card class="token-create-card" shadow="never">
          <template #header>{{ t('createApiToken') }}</template>
          <el-form label-position="top" @submit.prevent="createApiToken">
            <el-form-item :label="t('tokenName')"><el-input v-model="apiTokenForm.name" maxlength="80" show-word-limit /></el-form-item>
            <el-form-item :label="t('tokenScopes')"><el-checkbox-group v-model="apiTokenForm.scopes"><el-checkbox label="api">{{ t('apiScope') }}</el-checkbox><el-checkbox label="tokens:manage">{{ t('tokenManagementScope') }}</el-checkbox></el-checkbox-group></el-form-item>
            <el-form-item :label="t('expiresAt')"><el-date-picker v-model="apiTokenForm.expiresAt" type="datetime" value-format="YYYY-MM-DDTHH:mm:ss" :placeholder="t('noExpiry')" /></el-form-item>
            <el-button type="primary" :loading="apiTokenLoading" @click="createApiToken">{{ t('createApiToken') }}</el-button>
          </el-form>
        </el-card>
        <el-table :data="apiTokens" stripe class="token-table">
          <el-table-column prop="name" :label="t('tokenName')" min-width="180" />
          <el-table-column prop="token_prefix" :label="t('tokenPrefix')" min-width="150" />
          <el-table-column :label="t('tokenScopes')" min-width="170"><template #default="scope"><el-tag v-for="item in scope.row.scopes" :key="item" size="small" effect="plain">{{ item }}</el-tag></template></el-table-column>
          <el-table-column prop="created_at" :label="t('createdAt')" min-width="190"><template #default="scope">{{ formatDate(scope.row.created_at) }}</template></el-table-column>
          <el-table-column :label="t('tokenStatus')" width="120"><template #default="scope"><el-tag :type="scope.row.status === 'active' ? 'success' : 'info'">{{ scope.row.status === 'active' ? t('activeToken') : scope.row.status === 'expired' ? t('expiredToken') : t('revokedToken') }}</el-tag></template></el-table-column>
          <el-table-column :label="t('actions')" width="140"><template #default="scope"><el-button link type="danger" :disabled="scope.row.status !== 'active'" @click="revokeApiToken(scope.row)">{{ t('revokeToken') }}</el-button></template></el-table-column>
        </el-table>
        <el-empty v-if="!apiTokens.length" :description="t('noApiTokens')" />
      </el-card>
    </section>
</template>
