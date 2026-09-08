use crate::exec::CommandOutput;

#[derive(Debug, Clone)]
pub(crate) struct RedactedOutput {
    pub(crate) output: CommandOutput,
    pub(crate) count: usize,
}

pub(crate) fn redact_output(output: &CommandOutput) -> RedactedOutput {
    let (stdout, stdout_count) = redact_bytes(&output.stdout);
    let (stderr, stderr_count) = redact_bytes(&output.stderr);
    RedactedOutput {
        output: CommandOutput {
            status: output.status,
            stdout,
            stderr,
        },
        count: stdout_count + stderr_count,
    }
}

fn redact_bytes(bytes: &[u8]) -> (Vec<u8>, usize) {
    let (text, count) = redact_text(&String::from_utf8_lossy(bytes));
    (text.into_bytes(), count)
}

fn redact_text(text: &str) -> (String, usize) {
    let mut count = 0;
    let mut lines = Vec::new();
    for line in text.lines() {
        let mut redacted = line.to_string();
        count += redact_authorization_headers(&mut redacted);
        count += redact_key_value_secrets(&mut redacted);
        count += redact_secret_markers(&mut redacted);
        lines.push(redacted);
    }
    let mut rendered = lines.join("\n");
    if text.ends_with('\n') {
        rendered.push('\n');
    }
    (rendered, count)
}

fn redact_authorization_headers(text: &mut String) -> usize {
    let mut count = 0;
    let mut search_start = 0;
    while search_start < text.len() {
        let Some(relative_start) = text[search_start..]
            .to_ascii_lowercase()
            .find("authorization: bearer ")
        else {
            break;
        };
        let start = search_start + relative_start;
        let value_start = start + "authorization: bearer ".len();
        let end = find_secret_end(text, value_start);
        if text.get(value_start..end) == Some("[REDACTED]") {
            search_start = end;
            continue;
        }
        text.replace_range(value_start..end, "[REDACTED]");
        count += 1;
        search_start = value_start + "[REDACTED]".len();
    }
    count
}

fn redact_key_value_secrets(text: &mut String) -> usize {
    let mut count = 0;
    let secret_keys = [
        "access_token",
        "api_key",
        "apikey",
        "auth_token",
        "password",
        "secret",
        "token",
    ];
    let mut search_start = 0;
    loop {
        if search_start >= text.len() {
            break;
        }
        let lower = text[search_start..].to_ascii_lowercase();
        let Some((relative_key_start, key)) = secret_keys
            .iter()
            .filter_map(|key| lower.find(key).map(|index| (index, *key)))
            .min_by_key(|(index, _)| *index)
        else {
            break;
        };
        let key_start = search_start + relative_key_start;
        let key_end = key_start + key.len();
        let after_key = &text[key_end..];
        let Some(delimiter_offset) = after_key.char_indices().find_map(|(offset, ch)| match ch {
            '=' | ':' => Some(offset),
            '"' | '\'' | ' ' | '\t' => None,
            _ => Some(usize::MAX),
        }) else {
            break;
        };
        if delimiter_offset == usize::MAX {
            search_start = key_end;
            continue;
        }
        let delimiter = key_end + delimiter_offset;
        let mut value_start = delimiter + 1;
        while text
            .as_bytes()
            .get(value_start)
            .is_some_and(u8::is_ascii_whitespace)
        {
            value_start += 1;
        }
        let quote = text
            .as_bytes()
            .get(value_start)
            .copied()
            .filter(|byte| *byte == b'"' || *byte == b'\'');
        if quote.is_some() {
            value_start += 1;
        }
        let mut value_end = if let Some(quote) = quote {
            text.as_bytes()
                .get(value_start..)
                .and_then(|tail| tail.iter().position(|byte| *byte == quote))
                .map(|offset| value_start + offset)
                .unwrap_or_else(|| find_secret_end(text, value_start))
        } else {
            find_secret_end(text, value_start)
        };
        if value_end <= value_start {
            search_start = key_end;
            continue;
        }
        if quote.is_none() {
            value_end = value_end
                .min(
                    text[value_start..]
                        .find(',')
                        .map(|offset| value_start + offset)
                        .unwrap_or(text.len()),
                )
                .min(
                    text[value_start..]
                        .find('}')
                        .map(|offset| value_start + offset)
                        .unwrap_or(text.len()),
                );
        }
        text.replace_range(value_start..value_end, "[REDACTED]");
        count += 1;
        search_start = value_start + "[REDACTED]".len();
    }
    count
}

fn redact_secret_markers(text: &mut String) -> usize {
    let mut count = 0;
    for marker in ["sk-", "ghp_", "xoxb-"] {
        while let Some(start) = text.find(marker) {
            let end = find_secret_end(text, start);
            text.replace_range(start..end, "[REDACTED]");
            count += 1;
        }
    }
    count
}

fn find_secret_end(text: &str, start: usize) -> usize {
    text[start..]
        .char_indices()
        .find_map(|(offset, ch)| {
            if ch.is_whitespace() || matches!(ch, ',' | ';' | ')' | ']' | '}') {
                Some(start + offset)
            } else {
                None
            }
        })
        .unwrap_or(text.len())
}

#[cfg(test)]
mod tests {
    use super::redact_output;
    use crate::exec::CommandOutput;
    use std::process::Command;

    fn ok_status() -> std::process::ExitStatus {
        Command::new("sh")
            .arg("-c")
            .arg("exit 0")
            .status()
            .expect("status")
    }

    #[test]
    fn redacts_secret_like_stdout_and_stderr() {
        let output = CommandOutput {
            status: ok_status(),
            stdout: b"API_TOKEN=secret-value\nplain\nsk-live123\n".to_vec(),
            stderr: b"Authorization: Bearer bearer-secret\nghp_secret123\n".to_vec(),
        };

        let redacted = redact_output(&output);
        let stdout = String::from_utf8(redacted.output.stdout).expect("stdout utf8");
        let stderr = String::from_utf8(redacted.output.stderr).expect("stderr utf8");

        assert_eq!(redacted.count, 4);
        assert!(stdout.contains("API_TOKEN=[REDACTED]"));
        assert!(stdout.contains("[REDACTED]"));
        assert!(stderr.contains("Authorization: Bearer [REDACTED]"));
        assert!(!stdout.contains("secret-value"));
        assert!(!stdout.contains("sk-live123"));
        assert!(!stderr.contains("bearer-secret"));
        assert!(!stderr.contains("ghp_secret123"));
    }

    #[test]
    fn redacts_json_colon_and_repeated_secret_forms() {
        let output = CommandOutput {
            status: ok_status(),
            stdout:
                br#"{"access_token":"tok-1","api_key":"sk-json"} password: hunter2 sk-one sk-two"#
                    .to_vec(),
            stderr: b"Authorization: Bearer first Authorization: Bearer second\n".to_vec(),
        };

        let redacted = redact_output(&output);
        let stdout = String::from_utf8(redacted.output.stdout).expect("stdout utf8");
        let stderr = String::from_utf8(redacted.output.stderr).expect("stderr utf8");

        for secret in [
            "tok-1", "sk-json", "hunter2", "sk-one", "sk-two", "first", "second",
        ] {
            assert!(!stdout.contains(secret), "stdout leaked {secret}: {stdout}");
            assert!(!stderr.contains(secret), "stderr leaked {secret}: {stderr}");
        }
        assert!(redacted.count >= 7);
    }
}
