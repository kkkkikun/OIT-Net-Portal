package com.oitnetportal.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.FilterChip
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp

/** 反馈类型。取值与 OpenFeedback 服务端的分类常量一致。 */
enum class FeedbackCategory(val wireValue: String, val label: String) {
    BUG("bug", "问题"),
    FEATURE("feature", "功能建议"),
    EXPERIENCE("experience", "体验问题"),
    OTHER("other", "其他"),
}

/**
 * App 内的反馈表单。
 *
 * 全部在 App 内完成，不跳浏览器、不打开第三方问卷链接。
 * 表单不收集账号与密码：反馈内容只有同学主动填写的文字和可选的脱敏诊断摘要。
 */
@Composable
fun FeedbackForm(
    isSubmitting: Boolean,
    onSubmit: (FeedbackCategory, String, Boolean) -> Unit,
    onDismiss: () -> Unit,
) {
    // 默认选中「功能建议」：这与迁移前的默认分类（建议）语义一致。
    var category by remember { mutableStateOf(FeedbackCategory.FEATURE) }
    var content by remember { mutableStateOf("") }
    var withDiagnostics by remember { mutableStateOf(false) }
    var showValidationError by remember { mutableStateOf(false) }

    AlertDialog(
        onDismissRequest = { if (!isSubmitting) onDismiss() },
        title = { Text("意见反馈", style = MaterialTheme.typography.titleLarge, fontWeight = FontWeight.Bold) },
        text = {
            Column(
                Modifier.verticalScroll(rememberScrollState()),
                verticalArrangement = Arrangement.spacedBy(14.dp),
            ) {
                Text(
                    "遇到问题或有想法都欢迎提在这里。作者会集中处理后回复。",
                    style = MaterialTheme.typography.bodyMedium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
                Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
                    Text(
                        "反馈类型",
                        style = MaterialTheme.typography.titleSmall,
                        fontWeight = FontWeight.SemiBold,
                    )
                    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        FeedbackCategory.entries.forEach { option ->
                            FilterChip(
                                selected = category == option,
                                onClick = { category = option },
                                label = { Text(option.label) },
                            )
                        }
                    }
                }
                OutlinedTextField(
                    value = content,
                    onValueChange = {
                        content = it
                        if (showValidationError && it.isNotBlank()) showValidationError = false
                    },
                    label = { Text("说说你遇到的情况或建议") },
                    placeholder = { Text("例如：换到教学楼后经常连不上，需要手动重连") },
                    isError = showValidationError,
                    supportingText = if (showValidationError) {
                        { Text("内容不能为空") }
                    } else {
                        null
                    },
                    enabled = !isSubmitting,
                    minLines = 4,
                    modifier = Modifier.fillMaxWidth().heightIn(min = 120.dp),
                )
                Card(
                    colors = CardDefaults.cardColors(
                        containerColor = MaterialTheme.colorScheme.surfaceVariant,
                    ),
                ) {
                    Column(Modifier.padding(14.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                        Row(
                            Modifier.fillMaxWidth(),
                            verticalAlignment = Alignment.CenterVertically,
                        ) {
                            Column(Modifier.weight(1f)) {
                                Text(
                                    "附带诊断信息",
                                    style = MaterialTheme.typography.titleSmall,
                                    fontWeight = FontWeight.SemiBold,
                                )
                                Text(
                                    "附带最近连接状态，便于定位问题；不含账号、密码或上网记录。",
                                    style = MaterialTheme.typography.bodySmall,
                                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                                )
                            }
                            Switch(
                                checked = withDiagnostics,
                                onCheckedChange = { withDiagnostics = it },
                                enabled = !isSubmitting,
                            )
                        }
                    }
                }
                Text(
                    "反馈会发到作者的 OpenFeedback 后台，作者会集中处理后回复。" +
                        "断网时会先存在手机里，联网后自动补发。",
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
        },
        confirmButton = {
            Button(
                onClick = {
                    if (content.isBlank()) {
                        showValidationError = true
                        return@Button
                    }
                    onSubmit(category, content.trim(), withDiagnostics)
                },
                enabled = !isSubmitting,
            ) {
                Text(if (isSubmitting) "正在提交…" else "提交反馈")
            }
        },
        dismissButton = {
            TextButton(onClick = onDismiss, enabled = !isSubmitting) { Text("取消") }
        },
    )
}
