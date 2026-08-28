use futures_util::StreamExt;
use serde::{Deserialize, Serialize};
use std::process::{Command, Stdio};
use std::time::Duration;
use sysinfo::{Disks, System};
use tauri::Emitter;

const OLLAMA_BASE_URL: &str = "http://127.0.0.1:11434";
const BACKEND_HEALTH_URL: &str = "http://127.0.0.1:8000/health";

#[derive(Debug, Clone, Serialize)]
struct SystemReadiness {
    platform: String,
    arch: String,
    total_memory_bytes: u64,
    available_disk_bytes: u64,
    ollama_reachable: bool,
    ollama_version: Option<String>,
    installed_models: Vec<String>,
    docker_reachable: bool,
    backend_reachable: bool,
}

#[derive(Debug, Deserialize)]
struct OllamaVersion {
    version: Option<String>,
}

#[derive(Debug, Deserialize)]
struct OllamaTags {
    #[serde(default)]
    models: Vec<OllamaModel>,
}

#[derive(Debug, Deserialize)]
struct OllamaModel {
    name: String,
}

fn http_client() -> Result<reqwest::Client, String> {
    reqwest::Client::builder()
        .timeout(Duration::from_secs(3))
        .build()
        .map_err(|error| format!("Could not initialize the local service client: {error}"))
}

fn docker_command() -> Command {
    #[cfg(target_os = "macos")]
    {
        for candidate in ["/usr/local/bin/docker", "/opt/homebrew/bin/docker"] {
            if std::path::Path::new(candidate).exists() {
                return Command::new(candidate);
            }
        }
    }

    Command::new(if cfg!(target_os = "windows") {
        "docker.exe"
    } else {
        "docker"
    })
}

async fn endpoint_reachable(client: &reqwest::Client, url: &str) -> bool {
    client
        .get(url)
        .send()
        .await
        .map(|response| response.status().is_success())
        .unwrap_or(false)
}

#[tauri::command]
async fn get_system_readiness() -> Result<SystemReadiness, String> {
    let client = http_client()?;
    let mut system = System::new_all();
    system.refresh_memory();
    let disks = Disks::new_with_refreshed_list();
    let available_disk_bytes = disks
        .iter()
        .map(|disk| disk.available_space())
        .max()
        .unwrap_or_default();

    let version_response = client
        .get(format!("{OLLAMA_BASE_URL}/api/version"))
        .send()
        .await;
    let (ollama_reachable, ollama_version) = match version_response {
        Ok(response) if response.status().is_success() => {
            let version = response
                .json::<OllamaVersion>()
                .await
                .ok()
                .and_then(|payload| payload.version);
            (true, version)
        }
        _ => (false, None),
    };

    let installed_models = if ollama_reachable {
        match client
            .get(format!("{OLLAMA_BASE_URL}/api/tags"))
            .send()
            .await
        {
            Ok(response) if response.status().is_success() => response
                .json::<OllamaTags>()
                .await
                .map(|payload| payload.models.into_iter().map(|model| model.name).collect())
                .unwrap_or_default(),
            _ => Vec::new(),
        }
    } else {
        Vec::new()
    };

    let docker_reachable = tauri::async_runtime::spawn_blocking(|| {
        docker_command()
            .arg("info")
            .stdout(Stdio::null())
            .stderr(Stdio::null())
            .status()
            .map(|status| status.success())
            .unwrap_or(false)
    })
    .await
    .unwrap_or(false);

    Ok(SystemReadiness {
        platform: std::env::consts::OS.to_owned(),
        arch: std::env::consts::ARCH.to_owned(),
        total_memory_bytes: system.total_memory(),
        available_disk_bytes,
        ollama_reachable,
        ollama_version,
        installed_models,
        docker_reachable,
        backend_reachable: endpoint_reachable(&client, BACKEND_HEALTH_URL).await,
    })
}

fn valid_model_name(model: &str) -> bool {
    !model.is_empty()
        && model.len() <= 128
        && model
            .chars()
            .all(|character| character.is_ascii_alphanumeric() || ".:_/-".contains(character))
}

#[tauri::command]
async fn pull_ollama_model(app: tauri::AppHandle, model: String) -> Result<(), String> {
    if !valid_model_name(&model) {
        return Err("The requested Ollama model name is invalid.".to_owned());
    }

    let response = reqwest::Client::new()
        .post(format!("{OLLAMA_BASE_URL}/api/pull"))
        .json(&serde_json::json!({ "model": model, "stream": true }))
        .send()
        .await
        .map_err(|error| format!("Ollama is unavailable: {error}"))?
        .error_for_status()
        .map_err(|error| format!("Ollama rejected the model download: {error}"))?;

    let mut stream = response.bytes_stream();
    let mut pending = Vec::<u8>::new();
    while let Some(chunk) = stream.next().await {
        pending.extend_from_slice(
            &chunk.map_err(|error| format!("The model download was interrupted: {error}"))?,
        );
        while let Some(newline) = pending.iter().position(|byte| *byte == b'\n') {
            let line = pending.drain(..=newline).collect::<Vec<_>>();
            if let Ok(progress) = serde_json::from_slice::<serde_json::Value>(&line) {
                if let Some(error) = progress.get("error").and_then(|value| value.as_str()) {
                    return Err(format!("Ollama could not install the model: {error}"));
                }
                app.emit("ollama-model-progress", progress)
                    .map_err(|error| format!("Could not report model progress: {error}"))?;
            }
        }
    }

    if !pending.is_empty() {
        if let Ok(progress) = serde_json::from_slice::<serde_json::Value>(&pending) {
            if let Some(error) = progress.get("error").and_then(|value| value.as_str()) {
                return Err(format!("Ollama could not install the model: {error}"));
            }
            app.emit("ollama-model-progress", progress)
                .map_err(|error| format!("Could not report model progress: {error}"))?;
        }
    }

    Ok(())
}

#[tauri::command]
fn open_ollama_download() -> Result<(), String> {
    let url = if cfg!(target_os = "windows") {
        "https://ollama.com/download/windows"
    } else {
        "https://ollama.com/download/mac"
    };

    let status = if cfg!(target_os = "windows") {
        Command::new("cmd").args(["/C", "start", "", url]).status()
    } else {
        Command::new("open").arg(url).status()
    }
    .map_err(|error| format!("Could not open the Ollama download page: {error}"))?;

    if status.success() {
        Ok(())
    } else {
        Err("The operating system could not open the Ollama download page.".to_owned())
    }
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_process::init())
        .plugin(tauri_plugin_updater::Builder::new().build())
        .invoke_handler(tauri::generate_handler![
            get_system_readiness,
            pull_ollama_model,
            open_ollama_download
        ])
        .run(tauri::generate_context!())
        .expect("error while running the Legal RAG desktop application");
}
