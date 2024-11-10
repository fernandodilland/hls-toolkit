import os
import subprocess
import sys
from pathlib import Path
from tkinter import Tk, filedialog, messagebox

def select_file():
    root = Tk()
    root.withdraw()
    file_path = filedialog.askopenfilename(
        title="Selecciona el archivo de video",
        filetypes=[
            ("Archivos de video", "*.mp4 *.mkv *.avi *.mov *.flv *.wmv *.webm *.ts"),
            ("Todos los archivos", "*.*"),
        ],
    )
    root.destroy()
    return file_path

def select_destination():
    root = Tk()
    root.withdraw()
    folder_path = filedialog.askdirectory(title="Selecciona la carpeta de destino")
    root.destroy()
    return folder_path

def get_video_info(input_path):
    cmd = [
        "ffprobe",
        "-v", "error",
        "-select_streams", "v:0",
        "-show_entries", "stream=width,height",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        input_path,
    ]
    try:
        output = subprocess.check_output(cmd, stderr=subprocess.STDOUT).decode().strip().split('\n')
        if len(output) < 3:
            raise ValueError("ffprobe output incomplete. Asegúrate de que el archivo contiene video y duración.")
        width = int(output[0])
        height = int(output[1])
        duration_str = output[2]
        if duration_str.lower() == "n/a":
            raise ValueError("Duración no disponible en el archivo de video.")
        duration = float(duration_str)
        return width, height, duration
    except Exception as e:
        messagebox.showerror("Error", f"No se pudo obtener información del video: {e}")
        sys.exit(1)

def determine_resolutions(max_height):
    standard_resolutions = [144, 240, 360, 480, 720, 1080, 1440, 2160]
    return [res for res in standard_resolutions if res <= max_height]

def transcode_video(input_path, output_dir, resolutions):
    master_playlist = []
    for res in resolutions:
        res_dir = output_dir / f"{res}p"
        res_dir.mkdir(parents=True, exist_ok=True)
        playlist_path = res_dir / "index.m3u8"
        segment_path = res_dir / "segment_%03d.ts"
        
        # Determinar bitrate basado en la resolución
        bitrate = {
            144: "800k",
            240: "400k",
            360: "800k",
            480: "1400k",
            720: "2800k",
            1080: "5000k",
            1440: "8000k",
            2160: "14000k",
        }.get(res, "800k")
        
        cmd = [
            "ffmpeg",
            "-i", input_path,
            "-vf", f"scale=-2:{res}",
            "-pix_fmt", "yuv420p",  # Forzar a 8 bits
            "-profile:v", "high",   # Usar un perfil alto de H.264
            "-c:a", "aac",
            "-ar", "48000",
            "-b:a", "128k",
            "-c:v", "h264",
            "-crf", "20",
            "-g", "48",
            "-keyint_min", "48",
            "-sc_threshold", "0",
            "-b:v", bitrate,
            "-maxrate", bitrate,
            "-bufsize", "1000k",
            "-hls_time", "4",
            "-hls_playlist_type", "vod",
            "-hls_segment_filename", str(segment_path),
            str(playlist_path)
        ]
        print(f"Procesando resolución {res}p...")
        try:
            subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        except subprocess.CalledProcessError as e:
            messagebox.showerror("Error", f"FFmpeg falló en {res}p: {e.stderr.decode()}")
            sys.exit(1)
        
        # Añadir a la lista de master playlist
        master_playlist.append({
            "resolution": res,
            "bandwidth": bitrate_to_bandwidth(bitrate),
            "uri": f"{res}p/index.m3u8",
            "width": res * 16 // 9,  # Asumiendo aspect ratio 16:9
            "height": res
        })
    
    # Crear master.m3u8
    master_path = output_dir / "master.m3u8"
    with open(master_path, "w") as f:
        f.write("#EXTM3U\n#EXT-X-VERSION:3\n")
        for stream in master_playlist:
            f.write(
                f"#EXT-X-STREAM-INF:BANDWIDTH={stream['bandwidth']},RESOLUTION={stream['width']}x{stream['height']}\n"
                f"{stream['uri']}\n"
            )
    print("Master playlist creado.")
    return master_path

def bitrate_to_bandwidth(bitrate_str):
    # Convierte '800k' a 800000
    if bitrate_str.endswith('k'):
        return int(bitrate_str[:-1]) * 1000
    elif bitrate_str.endswith('M'):
        return int(float(bitrate_str[:-1]) * 1000000)
    else:
        return int(bitrate_str)

def generate_thumbnails(input_path, output_dir, duration, num_thumbnails=256):
    thumbnails_dir = output_dir / "thumbnails"
    thumbnails_dir.mkdir(parents=True, exist_ok=True)
    
    if num_thumbnails < 2:
        num_thumbnails = 2  # Asegura al menos dos miniaturas
    
    # Calcular intervalos, incluyendo el primer y último frame
    interval = duration / (num_thumbnails - 1)
    epsilon = 0.1  # Aumentar el margen de seguridad para el último timestamp
    timestamps = [0]  # Primer frame
    for i in range(1, num_thumbnails - 1):
        ts = interval * i
        # Asegurar que el timestamp no exceda la duración
        if ts >= duration:
            ts = duration - epsilon
        timestamps.append(ts)
    last_ts = duration - epsilon if duration > epsilon else 0
    timestamps.append(last_ts)  # Último frame
    
    # FFmpeg espera timestamps en formato HH:MM:SS.milliseconds
    timestamps_formatted = [seconds_to_timestamp(ts) for ts in timestamps]
    
    for idx, ts in enumerate(timestamps_formatted, start=1):
        thumb_path = thumbnails_dir / f"thumb{idx}.webp"
        thumbnail_size = "160x90" if idx < num_thumbnails else "120x68"  # Reducir la última miniatura
        cmd = [
            "ffmpeg",
            "-ss", ts,
            "-i", input_path,
            "-vframes", "1",
            "-s", thumbnail_size,  # Tamaño de la miniatura, reducido para la última
            "-f", "webp",
            "-y",  # Sobrescribir sin preguntar
            str(thumb_path)
        ]
        print(f"Generando miniatura {idx} en {ts}...")
        try:
            subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        except subprocess.CalledProcessError as e:
            messagebox.showerror("Error", f"FFmpeg falló al generar miniatura {idx}: {e.stderr.decode()}")
            sys.exit(1)
    
    print("Miniaturas generadas.")
    return thumbnails_dir

def seconds_to_timestamp(seconds):
    hrs = int(seconds // 3600)
    mins = int((seconds % 3600) // 60)
    secs = seconds % 60
    return f"{hrs:02}:{mins:02}:{secs:06.3f}"

def main():
    print("Seleccionando el archivo de video...")
    input_path = Path(select_file())
    if not input_path.exists():
        messagebox.showerror("Error", "El archivo de video seleccionado no existe.")
        sys.exit(1)
    
    print("Seleccionando la carpeta de destino...")
    output_dir = Path(select_destination())
    if not output_dir.exists():
        messagebox.showerror("Error", "La carpeta de destino seleccionada no existe.")
        sys.exit(1)
    
    print("Obteniendo información del video...")
    width, height, duration = get_video_info(str(input_path))
    print(f"Resolución: {width}x{height}, Duración: {duration} segundos")
    
    resolutions = determine_resolutions(height)
    if not resolutions:
        messagebox.showerror("Error", "No se encontraron resoluciones adecuadas para el video.")
        sys.exit(1)
    
    print(f"Resoluciones a procesar: {resolutions}")
    
    # Crear una carpeta para el proyecto
    project_name = input_path.stem
    project_dir = output_dir / project_name
    project_dir.mkdir(parents=True, exist_ok=True)
    
    print("Transcodificando el video a múltiples resoluciones...")
    master_playlist = transcode_video(str(input_path), project_dir, resolutions)
    
    print("Generando miniaturas...")
    generate_thumbnails(str(input_path), project_dir, duration)
    
    print(f"Proceso completado. Archivos almacenados en: {project_dir}")
    messagebox.showinfo("Completado", f"El procesamiento ha finalizado.\nCarpeta de salida: {project_dir}")

if __name__ == "__main__":
    main()
