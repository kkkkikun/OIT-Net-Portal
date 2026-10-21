package com.oitnetportal.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.unit.dp
import com.oitnetportal.core.AccountInfo

/**
 * 账号管理对话框：列出已保存账号（别名/用户名/绑定 Wi-Fi），支持编辑备注与
 * SSID 绑定、删除账号。对话框只展示脱敏元数据，永不显示密码；
 * 未授权 Wi-Fi 名称读取时提供授权入口。
 */
@Composable
fun AccountManagementDialog(
    accounts: List<AccountInfo>,
    wifiAutoMatchAvailable: Boolean,
    onRequestWifiPermission: () -> Unit,
    onUpdateMeta: (String, String, String) -> Unit,
    onDelete: (String) -> Unit,
    onDismiss: () -> Unit,
) {
    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text("账号管理") },
        text = {
            Column(
                modifier = Modifier.verticalScroll(rememberScrollState()),
                verticalArrangement = Arrangement.spacedBy(12.dp),
            ) {
                if (!wifiAutoMatchAvailable) {
                    Text(
                        "未授权读取 Wi-Fi 名称，无法按网络自动匹配账号。",
                        style = MaterialTheme.typography.bodySmall,
                    )
                    TextButton(
                        onClick = onRequestWifiPermission,
                        modifier = Modifier.semantics { contentDescription = "授权 Wi-Fi 名称读取" },
                    ) {
                        Text("授权 Wi-Fi 名称读取")
                    }
                }
                if (accounts.isEmpty()) {
                    Text("暂无已保存账号。勾选「保存此账号」并登录成功后会出现在这里。")
                }
                accounts.forEach { account ->
                    AccountRow(
                        account = account,
                        onUpdateMeta = onUpdateMeta,
                        onDelete = onDelete,
                    )
                }
            }
        },
        confirmButton = {
            TextButton(onClick = onDismiss) { Text("关闭") }
        },
    )
}

@Composable
private fun AccountRow(
    account: AccountInfo,
    onUpdateMeta: (String, String, String) -> Unit,
    onDelete: (String) -> Unit,
) {
    var editing by remember(account.id) { mutableStateOf(false) }
    var alias by remember(account.id) { mutableStateOf(account.alias) }
    var boundSsid by remember(account.id) { mutableStateOf(account.boundSsid) }

    Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
        Text(
            if (account.alias.isBlank()) account.username
            else "${account.alias}（${account.username}）",
            style = MaterialTheme.typography.titleSmall,
        )
        Text(
            if (account.boundSsid.isBlank()) "未绑定 Wi-Fi"
            else "绑定 Wi-Fi：${account.boundSsid}",
            style = MaterialTheme.typography.bodySmall,
        )
        if (editing) {
            OutlinedTextField(
                value = alias,
                onValueChange = { alias = it },
                label = { Text("备注名（如：学生号）") },
                singleLine = true,
                modifier = Modifier
                    .fillMaxWidth()
                    .semantics { contentDescription = "账号备注名输入框" },
            )
            OutlinedTextField(
                value = boundSsid,
                onValueChange = { boundSsid = it },
                label = { Text("绑定 Wi-Fi 名称（如：OIT-JIAOSHI，可留空）") },
                singleLine = true,
                modifier = Modifier
                    .fillMaxWidth()
                    .semantics { contentDescription = "账号绑定 Wi-Fi 输入框" },
            )
        }
        Row(
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            if (editing) {
                TextButton(
                    onClick = {
                        onUpdateMeta(account.id, alias, boundSsid)
                        editing = false
                    },
                    modifier = Modifier.semantics { contentDescription = "保存账号备注" },
                ) {
                    Text("保存")
                }
                TextButton(onClick = {
                    alias = account.alias
                    boundSsid = account.boundSsid
                    editing = false
                }) {
                    Text("取消")
                }
            } else {
                TextButton(
                    onClick = { editing = true },
                    modifier = Modifier.semantics { contentDescription = "编辑账号备注" },
                ) {
                    Text("编辑")
                }
            }
            TextButton(
                onClick = { onDelete(account.id) },
                modifier = Modifier.semantics { contentDescription = "删除账号" },
            ) {
                Text("删除")
            }
        }
    }
}
