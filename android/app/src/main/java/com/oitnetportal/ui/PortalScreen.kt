package com.oitnetportal.ui

import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.oitnetportal.core.AndroidWifiIdentityProvider
import com.oitnetportal.core.PortalStatus

private const val MAX_SHOWN_EVENTS = 10

@Composable
fun PortalApp(viewModel: PortalViewModel) {
    val state by viewModel.uiState.collectAsStateWithLifecycle()
    // Wi-Fi 名称读取权限：只在用户主动点击授权入口时发起申请
    val wifiPermissionLauncher = rememberLauncherForActivityResult(
        ActivityResultContracts.RequestPermission(),
    ) { viewModel.onWifiPermissionResult() }

    MaterialTheme {
        PortalScreen(
            state = state,
            onRefresh = viewModel::refresh,
            onLogin = viewModel::loginOnce,
            onCredentialsSubmit = viewModel::loginWithCredentials,
            onEndSession = viewModel::endLocalSession,
            onToggleNetworkRecovery = viewModel::setAutoRefreshOnNetworkRecovery,
            onToggleForegroundRefresh = viewModel::setAutoRefreshOnForeground,
            onSelectAccount = viewModel::selectAccount,
            onDeleteAccount = viewModel::deleteAccount,
            onUpdateAccountMeta = viewModel::updateAccountMeta,
            onRequestWifiPermission = {
                wifiPermissionLauncher.launch(AndroidWifiIdentityProvider.requiredPermission())
            },
        )
    }
}

@Composable
fun PortalScreen(
    state: PortalUiState,
    onRefresh: () -> Unit,
    onLogin: () -> Unit,
    onCredentialsSubmit: (String, String, Boolean) -> Unit,
    onEndSession: () -> Unit,
    onToggleNetworkRecovery: (Boolean) -> Unit = {},
    onToggleForegroundRefresh: (Boolean) -> Unit = {},
    onSelectAccount: (String) -> Unit = {},
    onDeleteAccount: (String) -> Unit = {},
    onUpdateAccountMeta: (String, String, String) -> Unit = { _, _, _ -> },
    onRequestWifiPermission: () -> Unit = {},
) {
    var showAccountManager by remember { mutableStateOf(false) }

    if (showAccountManager) {
        AccountManagementDialog(
            accounts = state.savedAccounts,
            wifiAutoMatchAvailable = state.wifiAutoMatchAvailable,
            onRequestWifiPermission = onRequestWifiPermission,
            onUpdateMeta = onUpdateAccountMeta,
            onDelete = onDeleteAccount,
            onDismiss = { showAccountManager = false },
        )
    }

    Scaffold { innerPadding ->
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(innerPadding)
                .verticalScroll(rememberScrollState())
                .padding(20.dp),
            verticalArrangement = Arrangement.spacedBy(16.dp),
        ) {
            Column {
                Text(
                    text = "OIT Net Portal",
                    style = MaterialTheme.typography.headlineMedium,
                    fontWeight = FontWeight.Bold,
                )
                Text(
                    text = "校园网自动登录与保活",
                    style = MaterialTheme.typography.bodyLarge,
                )
            }

            StatusCard(state)

            PortalCredentialForm(
                onSubmit = onCredentialsSubmit,
                isBusy = state.isBusy,
                prefill = state.prefill,
                savedAccounts = state.savedAccounts,
                onSelectAccount = onSelectAccount,
            )

            Card(modifier = Modifier.fillMaxWidth()) {
                Row(
                    modifier = Modifier
                        .fillMaxWidth()
                        .padding(16.dp),
                    horizontalArrangement = Arrangement.spacedBy(12.dp),
                ) {
                    Button(
                        onClick = onLogin,
                        enabled = state.coreAvailable && !state.isBusy,
                        modifier = Modifier.weight(1f),
                    ) {
                        Text("重试登录")
                    }
                    OutlinedButton(
                        onClick = onRefresh,
                        enabled = state.coreAvailable && !state.isBusy,
                        modifier = Modifier.weight(1f),
                    ) {
                        Text("刷新状态")
                    }
                }
            }

            Card(modifier = Modifier.fillMaxWidth()) {
                Column(
                    modifier = Modifier.padding(16.dp),
                    verticalArrangement = Arrangement.spacedBy(10.dp),
                ) {
                    Text("账号与会话", style = MaterialTheme.typography.titleMedium)
                    OutlinedButton(
                        onClick = { showAccountManager = true },
                        modifier = Modifier
                            .fillMaxWidth()
                            .semantics { contentDescription = "打开账号管理" },
                    ) {
                        Text("管理已保存账号（${state.savedAccounts.size}）")
                    }
                    Text("结束本次会话只关闭应用内 Python 认证会话，不会向校园网服务器发送退出请求，也不能保证当前校园网连接立刻断开。")
                    OutlinedButton(
                        onClick = onEndSession,
                        enabled = state.coreAvailable && !state.isBusy,
                        modifier = Modifier.fillMaxWidth(),
                    ) {
                        Text("结束本次会话")
                    }
                }
            }

            Card(modifier = Modifier.fillMaxWidth()) {
                Row(
                    modifier = Modifier
                        .fillMaxWidth()
                        .padding(16.dp),
                    verticalAlignment = Alignment.CenterVertically,
                    horizontalArrangement = Arrangement.spacedBy(16.dp),
                ) {
                    Column(modifier = Modifier.weight(1f)) {
                        Text("自动重连", style = MaterialTheme.typography.titleMedium)
                        Text("前台服务与 Python 守护桥接尚未接通")
                    }
                    Switch(
                        checked = false,
                        onCheckedChange = {},
                        enabled = false,
                    )
                }
            }

            Card(modifier = Modifier.fillMaxWidth()) {
                Column(
                    modifier = Modifier.padding(16.dp),
                    verticalArrangement = Arrangement.spacedBy(12.dp),
                ) {
                    Text("设置", style = MaterialTheme.typography.titleMedium)
                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        verticalAlignment = Alignment.CenterVertically,
                        horizontalArrangement = Arrangement.spacedBy(16.dp),
                    ) {
                        Column(modifier = Modifier.weight(1f)) {
                            Text("网络恢复时自动刷新", style = MaterialTheme.typography.titleSmall)
                            Text("Wi-Fi 恢复后自动校准连接状态，不会自动登录")
                        }
                        Switch(
                            checked = state.autoRefreshOnNetworkRecovery,
                            onCheckedChange = onToggleNetworkRecovery,
                        )
                    }
                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        verticalAlignment = Alignment.CenterVertically,
                        horizontalArrangement = Arrangement.spacedBy(16.dp),
                    ) {
                        Column(modifier = Modifier.weight(1f)) {
                            Text("回到前台时自动刷新", style = MaterialTheme.typography.titleSmall)
                            Text("应用回到前台时探测一次连接状态")
                        }
                        Switch(
                            checked = state.autoRefreshOnForeground,
                            onCheckedChange = onToggleForegroundRefresh,
                        )
                    }
                    OutlinedButton(
                        onClick = {},
                        enabled = false,
                        modifier = Modifier.fillMaxWidth(),
                    ) {
                        Text("协议 Capture（待接入）")
                    }
                }
            }

            Card(modifier = Modifier.fillMaxWidth()) {
                Column(
                    modifier = Modifier.padding(16.dp),
                    verticalArrangement = Arrangement.spacedBy(8.dp),
                ) {
                    Text("诊断事件", style = MaterialTheme.typography.titleMedium)
                    state.notice?.let { Text(it) }
                    if (state.events.isEmpty()) {
                        Text("暂无诊断事件；事件仅保留本次会话内的最近 50 条，均为脱敏文本。")
                    } else {
                        state.events.take(MAX_SHOWN_EVENTS).forEach { event ->
                            Text(event, style = MaterialTheme.typography.bodySmall)
                        }
                        if (state.events.size > MAX_SHOWN_EVENTS) {
                            Text(
                                "… 共 ${state.events.size} 条，仅展示最新 $MAX_SHOWN_EVENTS 条",
                                style = MaterialTheme.typography.bodySmall,
                            )
                        }
                    }
                }
            }
        }
    }
}

@Composable
private fun StatusCard(state: PortalUiState) {
    Card(modifier = Modifier.fillMaxWidth()) {
        Column(
            modifier = Modifier.padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            Text("连接状态", style = MaterialTheme.typography.titleMedium)
            Text(
                text = when (state.status) {
                    PortalStatus.UNKNOWN -> "未知"
                    PortalStatus.ONLINE -> "在线"
                    PortalStatus.CAPTIVE -> "待认证"
                    PortalStatus.OFFLINE -> "离线"
                },
                style = MaterialTheme.typography.headlineSmall,
            )
            Text(state.statusDetail)
            if (state.isBusy) {
                LinearProgressIndicator(modifier = Modifier.fillMaxWidth())
            }
        }
    }
}
