package com.oitnetportal.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.Checkbox
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
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
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.unit.dp
import com.oitnetportal.core.AccountInfo

/**
 * Reusable campus credential form.
 *
 * Password state is intentionally remembered only for this composition and is cleared before the
 * submit callback runs. Kotlin String cannot guarantee secure in-memory erasure; this component only
 * promises that it does not persist the password.
 *
 * 预填由外部传入的 prefill 载荷驱动（nonce 变化时重置字段）；账号下拉只负责回调选择，
 * 表单自身不做任何持久化。「保存此账号」默认不勾选，是否加密保存完全由用户显式选择。
 */
@Composable
fun PortalCredentialForm(
    onSubmit: (String, String, Boolean) -> Unit,
    modifier: Modifier = Modifier,
    enabled: Boolean = true,
    isBusy: Boolean = false,
    prefill: PrefillCredentials? = null,
    savedAccounts: List<AccountInfo> = emptyList(),
    onSelectAccount: (String) -> Unit = {},
) {
    var username by remember(prefill?.nonce) { mutableStateOf(prefill?.username ?: "") }
    var password by remember(prefill?.nonce) { mutableStateOf(prefill?.password ?: "") }
    var saveAccount by remember(prefill?.nonce) { mutableStateOf(prefill?.saveAccount ?: false) }
    var showValidationErrors by remember { mutableStateOf(false) }
    val canInteract = enabled && !isBusy

    fun submit() {
        if (!canInteract) return

        val usernameBlank = username.isBlank()
        val passwordBlank = password.isBlank()
        showValidationErrors = usernameBlank || passwordBlank
        val submittedPassword = password
        password = ""
        if (usernameBlank || passwordBlank) return

        onSubmit(username.trim(), submittedPassword, saveAccount)
    }

    Card(modifier = modifier.fillMaxWidth()) {
        Column(
            modifier = Modifier.padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            Text("校园网账号", style = MaterialTheme.typography.titleMedium)
            Text("凭据仅用于本次登录；勾选「保存此账号」才会经 Android Keystore 加密后保存在本机。")

            if (savedAccounts.isNotEmpty()) {
                AccountPicker(
                    accounts = savedAccounts,
                    selectedId = prefill?.accountId,
                    enabled = canInteract,
                    onSelect = onSelectAccount,
                )
            }

            OutlinedTextField(
                value = username,
                onValueChange = { username = it },
                modifier = Modifier
                    .fillMaxWidth()
                    .semantics { contentDescription = "校园网账号输入框" },
                enabled = canInteract,
                label = { Text("学号或工号") },
                isError = showValidationErrors && username.isBlank(),
                supportingText = {
                    if (showValidationErrors && username.isBlank()) {
                        Text("请输入校园网账号")
                    }
                },
                singleLine = true,
                keyboardOptions = KeyboardOptions(
                    keyboardType = KeyboardType.Text,
                    imeAction = ImeAction.Next,
                ),
            )

            OutlinedTextField(
                value = password,
                onValueChange = { password = it },
                modifier = Modifier
                    .fillMaxWidth()
                    .semantics { contentDescription = "校园网密码输入框" },
                enabled = canInteract,
                label = { Text("密码") },
                isError = showValidationErrors && password.isBlank(),
                supportingText = {
                    if (showValidationErrors && password.isBlank()) {
                        Text("请输入校园网密码")
                    }
                },
                singleLine = true,
                visualTransformation = PasswordVisualTransformation(),
                keyboardOptions = KeyboardOptions(
                    keyboardType = KeyboardType.Password,
                    imeAction = ImeAction.Done,
                ),
                keyboardActions = KeyboardActions(
                    onDone = { submit() },
                ),
            )

            Row(
                modifier = Modifier.fillMaxWidth(),
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.spacedBy(8.dp),
            ) {
                Checkbox(
                    checked = saveAccount,
                    onCheckedChange = { saveAccount = it },
                    enabled = canInteract,
                    modifier = Modifier.semantics { contentDescription = "保存此账号勾选框" },
                )
                Text("保存此账号（仅本机加密保存，不会自动登录）")
            }

            Button(
                onClick = { submit() },
                enabled = canInteract,
                modifier = Modifier
                    .fillMaxWidth()
                    .semantics { contentDescription = "提交校园网登录凭据" },
            ) {
                Text(if (isBusy) "正在提交…" else "登录")
            }
        }
    }
}

/** 已保存账号下拉选择器；展示别名+用户名，不展示密码。 */
@Composable
private fun AccountPicker(
    accounts: List<AccountInfo>,
    selectedId: String?,
    enabled: Boolean,
    onSelect: (String) -> Unit,
) {
    var expanded by remember { mutableStateOf(false) }
    val selected = accounts.firstOrNull { it.id == selectedId }

    Box(modifier = Modifier.fillMaxWidth()) {
        OutlinedButton(
            onClick = { expanded = true },
            enabled = enabled,
            modifier = Modifier
                .fillMaxWidth()
                .semantics { contentDescription = "选择已保存账号" },
        ) {
            Text(
                selected?.let { "当前账号：${it.displayLabel()}" }
                    ?: "选择已保存账号（${accounts.size}）",
            )
        }
        DropdownMenu(
            expanded = expanded,
            onDismissRequest = { expanded = false },
        ) {
            accounts.forEach { account ->
                DropdownMenuItem(
                    text = {
                        Text(
                            account.displayLabel() +
                                if (account.boundSsid.isNotBlank()) "（绑定 ${account.boundSsid}）" else "",
                        )
                    },
                    onClick = {
                        expanded = false
                        onSelect(account.id)
                    },
                )
            }
        }
    }
}

private fun AccountInfo.displayLabel(): String =
    if (alias.isBlank()) username else "$alias（$username）"
