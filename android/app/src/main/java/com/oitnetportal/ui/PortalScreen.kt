package com.oitnetportal.ui

import android.Manifest
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Build
import android.provider.Settings
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.core.content.ContextCompat
import com.oitnetportal.core.AndroidWifiIdentityProvider
import com.oitnetportal.core.BackgroundReconnectStatus
import com.oitnetportal.core.PortalStatus

private const val MAX_SHOWN_EVENTS = 10
private enum class PortalTab(val title: String, val symbol: String) {
    CONNECT("连接", "⌂"), SETTINGS("设置", "⚙"), DIAGNOSTICS("诊断", "≋")
}

@Composable
fun PortalApp(viewModel: PortalViewModel) {
    val state by viewModel.uiState.collectAsStateWithLifecycle()
    val context = LocalContext.current
    val wifiPermissionLauncher = rememberLauncherForActivityResult(
        ActivityResultContracts.RequestPermission(),
    ) { viewModel.onWifiPermissionResult() }
    val notificationPermissionLauncher = rememberLauncherForActivityResult(
        ActivityResultContracts.RequestPermission(),
    ) { granted -> viewModel.onBackgroundNotificationPermissionResult(granted) }
    OitPortalTheme {
        PortalScreen(
            state = state,
            onRefresh = viewModel::refresh,
            onLogin = viewModel::loginOnce,
            onCredentialsSubmit = viewModel::loginWithCredentials,
            onEndSession = viewModel::endLocalSession,
            onToggleNetworkRecovery = viewModel::setAutoRefreshOnNetworkRecovery,
            onToggleForegroundRefresh = viewModel::setAutoRefreshOnForeground,
            onToggleBackgroundReconnect = { enabled ->
                val needsPermission = Build.VERSION.SDK_INT >= 33 &&
                    ContextCompat.checkSelfPermission(
                        context,
                        Manifest.permission.POST_NOTIFICATIONS,
                    ) != PackageManager.PERMISSION_GRANTED
                if (enabled && needsPermission && viewModel.canEnableBackgroundReconnect()) {
                    notificationPermissionLauncher.launch(Manifest.permission.POST_NOTIFICATIONS)
                } else {
                    viewModel.setBackgroundAutoReconnect(enabled)
                }
            },
            onSelectAccount = viewModel::selectAccount,
            onDeleteAccount = viewModel::deleteAccount,
            onUpdateAccountMeta = viewModel::updateAccountMeta,
            onRequestWifiPermission = {
                wifiPermissionLauncher.launch(AndroidWifiIdentityProvider.requiredPermission())
            },
            onOpenNotificationSettings = {
                val intent = Intent(Settings.ACTION_APP_NOTIFICATION_SETTINGS)
                    .putExtra(Settings.EXTRA_APP_PACKAGE, context.packageName)
                try {
                    context.startActivity(intent)
                } catch (_: android.content.ActivityNotFoundException) {
                    // 个别 ROM 缺少该入口；提示用户手动到系统设置里找通知管理。
                    context.startActivity(
                        Intent(Settings.ACTION_APPLICATION_DETAILS_SETTINGS)
                            .setData(android.net.Uri.fromParts("package", context.packageName, null)),
                    )
                }
            },
            onSubmitFeedback = { category, content, withDiagnostics ->
                viewModel.submitFeedback(category, content, withDiagnostics)
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
    onToggleBackgroundReconnect: (Boolean) -> Unit = {},
    onSelectAccount: (String) -> Unit = {},
    onDeleteAccount: (String) -> Unit = {},
    onUpdateAccountMeta: (String, String, String) -> Unit = { _, _, _ -> },
    onRequestWifiPermission: () -> Unit = {},
    onOpenNotificationSettings: () -> Unit = {},
    onSubmitFeedback: (FeedbackCategory, String, Boolean) -> Unit = { _, _, _ -> },
) {
    var showAccountManager by remember { mutableStateOf(false) }
    var showFeedbackForm by remember { mutableStateOf(false) }
    var selectedTab by remember { mutableIntStateOf(0) }
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
    if (showFeedbackForm) {
        // 提交成功后自动收起表单，让设置页给出「已收到」的结果反馈。
        LaunchedEffect(state.feedbackSubmitted) {
            if (state.feedbackSubmitted) showFeedbackForm = false
        }
        FeedbackForm(
            isSubmitting = state.isSubmittingFeedback,
            onSubmit = { category, content, withDiagnostics ->
                onSubmitFeedback(category, content, withDiagnostics)
            },
            onDismiss = { showFeedbackForm = false },
        )
    }
    Scaffold(
        containerColor = MaterialTheme.colorScheme.background,
        bottomBar = {
            NavigationBar(containerColor = MaterialTheme.colorScheme.surface, tonalElevation = 0.dp) {
                PortalTab.entries.forEachIndexed { index, tab ->
                    NavigationBarItem(
                        selected = selectedTab == index,
                        onClick = { selectedTab = index },
                        icon = { Text(tab.symbol, style = MaterialTheme.typography.titleLarge) },
                        label = { Text(tab.title) },
                    )
                }
            }
        },
    ) { padding ->
        when (PortalTab.entries[selectedTab]) {
            PortalTab.CONNECT -> ConnectPage(
                state, Modifier.padding(padding), onRefresh, onLogin,
                onCredentialsSubmit, onSelectAccount,
            )
            PortalTab.SETTINGS -> SettingsPage(
                state, Modifier.padding(padding), onToggleNetworkRecovery,
                onToggleForegroundRefresh, onToggleBackgroundReconnect,
                { showAccountManager = true }, onEndSession,
                onOpenNotificationSettings,
                { showFeedbackForm = true },
            )
            PortalTab.DIAGNOSTICS -> DiagnosticsPage(state, Modifier.padding(padding))
        }
    }
}

@Composable
private fun ConnectPage(
    state: PortalUiState,
    modifier: Modifier = Modifier,
    onRefresh: () -> Unit,
    onLogin: () -> Unit,
    onCredentialsSubmit: (String, String, Boolean) -> Unit,
    onSelectAccount: (String) -> Unit,
) {
    Column(
        modifier.fillMaxSize().verticalScroll(rememberScrollState())
            .padding(horizontal = 20.dp, vertical = 16.dp),
        verticalArrangement = Arrangement.spacedBy(18.dp),
    ) {
        Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
            Box(
                Modifier.size(48.dp).background(MaterialTheme.colorScheme.primary, MaterialTheme.shapes.medium),
                contentAlignment = Alignment.Center,
            ) {
                Text("O", color = Color.White, style = MaterialTheme.typography.headlineMedium,
                    fontWeight = FontWeight.Bold)
            }
            Spacer(Modifier.width(12.dp))
            Column(Modifier.weight(1f)) {
                Text("OIT Net Portal", style = MaterialTheme.typography.titleLarge,
                    fontWeight = FontWeight.Bold)
                Text("校园网连接助手", style = MaterialTheme.typography.bodyMedium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant)
            }
            Surface(color = MaterialTheme.colorScheme.secondaryContainer, shape = CircleShape) {
                Text(
                    if (state.coreAvailable) "已就绪" else "待登录",
                    Modifier.padding(horizontal = 11.dp, vertical = 7.dp),
                    style = MaterialTheme.typography.labelMedium,
                    color = MaterialTheme.colorScheme.onSecondaryContainer,
                )
            }
        }
        StatusCard(state)
        state.notice?.let { notice ->
            Card(colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.primaryContainer)) {
                Row(Modifier.padding(16.dp), verticalAlignment = Alignment.Top) {
                    Text("提示", color = MaterialTheme.colorScheme.onPrimaryContainer,
                        fontWeight = FontWeight.SemiBold)
                    Spacer(Modifier.width(12.dp))
                    Text(notice, color = MaterialTheme.colorScheme.onPrimaryContainer,
                        style = MaterialTheme.typography.bodyMedium)
                }
            }
        }
        Column(verticalArrangement = Arrangement.spacedBy(5.dp)) {
            Text("连接校园网", style = MaterialTheme.typography.titleLarge, fontWeight = FontWeight.Bold)
            Text("输入校园网账号完成认证。保存账号为可选操作，不会自动登录。",
                style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.onSurfaceVariant)
        }
        PortalCredentialForm(
            onSubmit = onCredentialsSubmit,
            isBusy = state.isBusy,
            prefill = state.prefill,
            savedAccounts = state.savedAccounts,
            onSelectAccount = onSelectAccount,
        )
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(12.dp)) {
            Button(
                onClick = onLogin, enabled = state.coreAvailable && !state.isBusy,
                modifier = Modifier.weight(1f).height(52.dp),
            ) { Text("重试登录") }
            OutlinedButton(
                onClick = onRefresh, enabled = state.coreAvailable && !state.isBusy,
                modifier = Modifier.weight(1f).height(52.dp),
            ) { Text("刷新状态") }
        }
        Text("连接状态以实际探测结果为准；如果校园网需要人工验证，应用会提示你。",
            style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
    }
}

@Composable
private fun SettingsPage(
    state: PortalUiState,
    modifier: Modifier = Modifier,
    onToggleNetworkRecovery: (Boolean) -> Unit,
    onToggleForegroundRefresh: (Boolean) -> Unit,
    onToggleBackgroundReconnect: (Boolean) -> Unit,
    onManageAccounts: () -> Unit,
    onEndSession: () -> Unit,
    onOpenNotificationSettings: () -> Unit,
    onOpenFeedback: () -> Unit,
) {
    Column(
        modifier.fillMaxSize().verticalScroll(rememberScrollState())
            .padding(horizontal = 20.dp, vertical = 18.dp),
        verticalArrangement = Arrangement.spacedBy(18.dp),
    ) {
        PageHeading("PREFERENCES", "设置", "按你的使用习惯调整连接体验。")
        Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
            Text("连接行为", style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.SemiBold)
            Text("这些选项只会刷新连接状态，不会在后台自动提交账号密码。",
                style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
        }
        Card(colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface)) {
            Column {
                SettingSwitchRow("网络恢复时自动刷新", "Wi-Fi 恢复并通过系统验证后检查连接状态。",
                    state.autoRefreshOnNetworkRecovery, onToggleNetworkRecovery)
                HorizontalDivider(color = MaterialTheme.colorScheme.outline.copy(alpha = 0.6f))
                SettingSwitchRow("回到前台时自动刷新", "重新打开应用时检查一次当前状态。",
                    state.autoRefreshOnForeground, onToggleForegroundRefresh)
            }
        }
        Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
            Text("账号与安全", style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.SemiBold)
            Text("已保存账号仅在本机加密保存；密码不会展示在账号列表中。",
                style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
        }
        Card(colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface)) {
            Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Column(Modifier.weight(1f)) {
                        Text("已保存账号", style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.SemiBold)
                        Text("${state.savedAccounts.size} 个账号保存在本机",
                            style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                    }
                    OutlinedButton(onClick = onManageAccounts, modifier = Modifier.semantics { contentDescription = "管理已保存账号" }) { Text("管理") }
                }
                HorizontalDivider(color = MaterialTheme.colorScheme.outline.copy(alpha = 0.6f))
                Text("本地认证会话", style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.SemiBold)
                Text("结束本次会话会关闭应用内与后台 Python 认证会话，不会向校园网服务器发送退出请求，也不能保证当前校园网连接立刻断开。",
                    style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                OutlinedButton(
                    onClick = onEndSession,
                    enabled = (state.coreAvailable || state.backgroundAutoReconnectEnabled) && !state.isBusy,
                    modifier = Modifier.fillMaxWidth().height(48.dp),
                ) { Text("结束本次会话") }
            }
        }
        Card(colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceVariant)) {
            Column {
                SettingSwitchRow("后台自动重连",
                    state.backgroundReconnectDetail,
                    state.backgroundAutoReconnectEnabled,
                    onToggleBackgroundReconnect,
                )
                state.notice?.let {
                    Text(
                        it,
                        Modifier.padding(horizontal = 16.dp, vertical = 8.dp),
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
                OutlinedButton(
                    onClick = {},
                    enabled = false,
                    modifier = Modifier.fillMaxWidth().padding(16.dp),
                ) { Text("协议 Capture（待接入）") }
            }
        }
        if (state.backgroundAutoReconnectEnabled && !state.notificationsEnabled) {
            Card(colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.errorContainer)) {
                Column(
                    Modifier.padding(16.dp),
                    verticalArrangement = Arrangement.spacedBy(10.dp),
                ) {
                    Text(
                        "系统通知已被关闭",
                        style = MaterialTheme.typography.titleSmall,
                        fontWeight = FontWeight.SemiBold,
                        color = MaterialTheme.colorScheme.onErrorContainer,
                    )
                    Text(
                        "后台自动重连仍在运行，但常驻通知与登录失败提醒不会显示。" +
                            "部分厂商系统默认禁用应用通知，需要手动允许。",
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onErrorContainer,
                    )
                    OutlinedButton(
                        onClick = onOpenNotificationSettings,
                        modifier = Modifier.fillMaxWidth(),
                    ) { Text("打开通知设置") }
                }
            }
        }
        Card(colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface)) {
            Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
                Text("意见反馈", style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.SemiBold)
                Text(
                    "遇到问题或者有想法，直接在这里告诉作者；不用另外打开网页或加群。",
                    style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
                OutlinedButton(
                    onClick = onOpenFeedback,
                    modifier = Modifier.fillMaxWidth().height(48.dp),
                ) { Text("写一条反馈") }
                state.feedbackError?.let {
                    Text(
                        it,
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.error,
                    )
                }
                if (state.feedbackSubmitted) {
                    Text(
                        "反馈已收到，谢谢你的建议。",
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
            }
        }
    }
}

@Composable
private fun DiagnosticsPage(state: PortalUiState, modifier: Modifier = Modifier) {
    Column(
        modifier.fillMaxSize().verticalScroll(rememberScrollState())
            .padding(horizontal = 20.dp, vertical = 18.dp),
        verticalArrangement = Arrangement.spacedBy(18.dp),
    ) {
        PageHeading("CONNECTION LOG", "诊断", "帮助你理解最近的连接变化。")
        Card(colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface)) {
            Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
                Text("当前状态", style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.SemiBold)
                Row(verticalAlignment = Alignment.CenterVertically) {
                    StatusDot(state.status)
                    Spacer(Modifier.width(10.dp))
                    Text(statusLabel(state.status), style = MaterialTheme.typography.titleLarge, fontWeight = FontWeight.Bold)
                }
                Text(state.statusDetail, style = MaterialTheme.typography.bodyMedium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant)
                state.notice?.let {
                    HorizontalDivider(color = MaterialTheme.colorScheme.outline.copy(alpha = 0.6f))
                    Text(it, style = MaterialTheme.typography.bodyMedium)
                }
                if (state.backgroundReconnectStatus != BackgroundReconnectStatus.STOPPED) {
                    HorizontalDivider(color = MaterialTheme.colorScheme.outline.copy(alpha = 0.6f))
                    Text(
                        "后台自动重连：${state.backgroundReconnectDetail}",
                        style = MaterialTheme.typography.bodyMedium,
                    )
                }
            }
        }
        Card(colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface)) {
            Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(14.dp)) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Column(Modifier.weight(1f)) {
                        Text("诊断事件", style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.SemiBold)
                        Text("本次会话最多保留 50 条脱敏事件", style = MaterialTheme.typography.bodySmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant)
                    }
                    Surface(color = MaterialTheme.colorScheme.secondaryContainer, shape = CircleShape) {
                        Text("${state.events.size}", Modifier.padding(horizontal = 12.dp, vertical = 7.dp),
                            color = MaterialTheme.colorScheme.onSecondaryContainer, style = MaterialTheme.typography.labelLarge)
                    }
                }
                if (state.events.isEmpty()) {
                    Text("暂无诊断事件。连接操作发生后，相关记录会显示在这里。",
                        style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.onSurfaceVariant)
                } else {
                    state.events.take(MAX_SHOWN_EVENTS).forEachIndexed { index, event ->
                        Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.Top,
                            horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                            Box(Modifier.padding(top = 5.dp).size(8.dp).background(
                                if (index == 0) MaterialTheme.colorScheme.primary else MaterialTheme.colorScheme.outline,
                                CircleShape))
                            Text(event, style = MaterialTheme.typography.bodyMedium, modifier = Modifier.weight(1f))
                        }
                        if (index != state.events.take(MAX_SHOWN_EVENTS).lastIndex) {
                            HorizontalDivider(color = MaterialTheme.colorScheme.outline.copy(alpha = 0.45f))
                        }
                    }
                    if (state.events.size > MAX_SHOWN_EVENTS) {
                        Text("共 ${state.events.size} 条，仅展示最新 $MAX_SHOWN_EVENTS 条",
                            style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                    }
                }
            }
        }
        Text("日志只用于当前会话排障，不包含明文密码或完整会话凭据。",
            style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
    }
}

@Composable
private fun StatusCard(state: PortalUiState) {
    val tint = statusColor(state.status)
    Card(colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface)) {
        Column(Modifier.padding(20.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
            Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
                Column(Modifier.weight(1f)) {
                    Text("连接状态", style = MaterialTheme.typography.titleMedium,
                        color = MaterialTheme.colorScheme.onSurfaceVariant)
                    Spacer(Modifier.height(8.dp))
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        StatusDot(state.status)
                        Spacer(Modifier.width(10.dp))
                        Text(statusLabel(state.status), style = MaterialTheme.typography.headlineMedium,
                            fontWeight = FontWeight.Bold, color = tint)
                    }
                }
                Surface(color = tint.copy(alpha = 0.10f), shape = CircleShape) {
                    Text(when (state.status) {
                        PortalStatus.ONLINE -> "CONNECTED"
                        PortalStatus.CAPTIVE -> "ACTION NEEDED"
                        PortalStatus.OFFLINE -> "OFFLINE"
                        PortalStatus.UNKNOWN -> if (state.isBusy) "CHECKING" else "NOT CHECKED"
                    }, Modifier.padding(horizontal = 10.dp, vertical = 7.dp),
                        style = MaterialTheme.typography.labelSmall, color = tint)
                }
            }
            Text(state.statusDetail, style = MaterialTheme.typography.bodyMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant)
            if (state.isBusy) {
                LinearProgressIndicator(Modifier.fillMaxWidth(), color = MaterialTheme.colorScheme.primary)
                Text("正在检查连接，请稍候…", style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant)
            }
        }
    }
}

@Composable
private fun StatusDot(status: PortalStatus) {
    Box(Modifier.size(10.dp).background(statusColor(status), CircleShape)
        .semantics { contentDescription = statusLabel(status) })
}

@Composable
private fun PageHeading(eyebrow: String, title: String, subtitle: String) {
    Column(verticalArrangement = Arrangement.spacedBy(5.dp)) {
        Text(eyebrow, style = MaterialTheme.typography.labelMedium,
            color = MaterialTheme.colorScheme.primary, fontWeight = FontWeight.Bold)
        Text(title, style = MaterialTheme.typography.headlineMedium, fontWeight = FontWeight.Bold)
        Text(subtitle, style = MaterialTheme.typography.bodyMedium,
            color = MaterialTheme.colorScheme.onSurfaceVariant)
    }
}

@Composable
private fun SettingSwitchRow(
    title: String, description: String, checked: Boolean, onCheckedChange: (Boolean) -> Unit,
) {
    Row(Modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 15.dp),
        verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(16.dp)) {
        Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(5.dp)) {
            Text(title, style = MaterialTheme.typography.titleSmall, fontWeight = FontWeight.SemiBold)
            Text(description, style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant)
        }
        Switch(checked = checked, onCheckedChange = onCheckedChange)
    }
}

private fun statusLabel(status: PortalStatus): String = when (status) {
    PortalStatus.UNKNOWN -> "尚未确认"
    PortalStatus.ONLINE -> "校园网已连接"
    PortalStatus.CAPTIVE -> "需要认证"
    PortalStatus.OFFLINE -> "当前离线"
}
private fun statusColor(status: PortalStatus): Color = when (status) {
    PortalStatus.UNKNOWN -> Color(0xFF4569A8)
    PortalStatus.ONLINE -> Color(0xFF16805D)
    PortalStatus.CAPTIVE -> Color(0xFFAD6A0A)
    PortalStatus.OFFLINE -> Color(0xFFBA3444)
}
