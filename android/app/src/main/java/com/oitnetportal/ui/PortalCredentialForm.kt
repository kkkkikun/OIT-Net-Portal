package com.oitnetportal.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.unit.dp

/**
 * Reusable campus credential form.
 *
 * Password state is intentionally remembered only for this composition and is cleared before the
 * submit callback runs. Kotlin String cannot guarantee secure in-memory erasure; this component only
 * promises that it does not persist the password.
 */
@Composable
fun PortalCredentialForm(
    onSubmit: (String, String) -> Unit,
    modifier: Modifier = Modifier,
    enabled: Boolean = true,
    isBusy: Boolean = false,
) {
    var username by remember { mutableStateOf("") }
    var password by remember { mutableStateOf("") }
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

        onSubmit(username.trim(), submittedPassword)
    }

    Card(modifier = modifier.fillMaxWidth()) {
        Column(
            modifier = Modifier.padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            Text("校园网账号", style = MaterialTheme.typography.titleMedium)
            Text("凭据仅用于本次登录；此表单不会保存密码。")

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
