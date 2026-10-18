package com.oitnetportal.ui

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
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.oitnetportal.core.PortalStatus

@Composable
fun PortalApp(viewModel: PortalViewModel) {
    val state by viewModel.uiState.collectAsStateWithLifecycle()

    MaterialTheme {
        PortalScreen(
            state = state,
            onRefresh = viewModel::refresh,
            onLogin = viewModel::loginOnce,
        )
    }
}

@Composable
fun PortalScreen(
    state: PortalUiState,
    onRefresh: () -> Unit,
    onLogin: () -> Unit,
) {
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

            Card(modifier = Modifier.fillMaxWidth()) {
                Row(
                    modifier = Modifier
                        .fillMaxWidth()
                        .padding(16.dp),
                    horizontalArrangement = Arrangement.spacedBy(12.dp),
                ) {
                    Button(
                        onClick = onLogin,
                        enabled = !state.isBusy,
                        modifier = Modifier.weight(1f),
                    ) {
                        Text("手动登录")
                    }
                    OutlinedButton(
                        onClick = onRefresh,
                        enabled = !state.isBusy,
                        modifier = Modifier.weight(1f),
                    ) {
                        Text("刷新状态")
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
                    Text("协议与配置", style = MaterialTheme.typography.titleMedium)
                    OutlinedButton(
                        onClick = {},
                        enabled = false,
                        modifier = Modifier.fillMaxWidth(),
                    ) {
                        Text("协议 Capture（待接入）")
                    }
                    OutlinedButton(
                        onClick = {},
                        enabled = false,
                        modifier = Modifier.fillMaxWidth(),
                    ) {
                        Text("设置（待实现）")
                    }
                }
            }

            Card(modifier = Modifier.fillMaxWidth()) {
                Column(
                    modifier = Modifier.padding(16.dp),
                    verticalArrangement = Arrangement.spacedBy(8.dp),
                ) {
                    Text("日志与错误", style = MaterialTheme.typography.titleMedium)
                    Text(state.notice ?: "暂无诊断事件；文件日志查看尚未接入。")
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
