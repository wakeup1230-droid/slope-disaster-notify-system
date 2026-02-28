import tkinter as tk
from tkinter import ttk, messagebox
from PIL import Image, ImageTk
import pandas as pd
from geopy.distance import geodesic

# 讀取數據
data_file_path = r'C:\00_Python\06_coordinate_lookup\(11307)14省道公路路線里程牌(指45)KMZ.csv'
data = pd.read_csv(data_file_path)
data['牌面內容'] = data['牌面內容'].astype(str).str.replace('K', '').astype(float)

def get_coordinates(road_number, stake_number):
    filtered_data = data[(data['公路編號'] == road_number) & (data['牌面內容'] == stake_number)]
    
    if not filtered_data.empty:
        twd97_x = filtered_data.iloc[0]['坐標-X-TWD97']
        twd97_y = filtered_data.iloc[0]['坐標-Y-TWD97']
        wgs84_x = filtered_data.iloc[0]['坐標-X-WGS84']
        wgs84_y = filtered_data.iloc[0]['坐標-Y-WGS84']
        return (twd97_x, twd97_y), (wgs84_x, wgs84_y)
    else:
        return interpolate_coordinates(road_number, stake_number)

def interpolate_coordinates(road_number, stake_number):
    lower_bound = data[(data['公路編號'] == road_number) & (data['牌面內容'] <= stake_number)].sort_values(by='牌面內容', ascending=False).head(1)
    upper_bound = data[(data['公路編號'] == road_number) & (data['牌面內容'] >= stake_number)].sort_values(by='牌面內容').head(1)
    
    if lower_bound.empty or upper_bound.empty:
        return None, None
    
    lower_stake = lower_bound.iloc[0]['牌面內容']
    upper_stake = upper_bound.iloc[0]['牌面內容']
    
    coords_lower_wgs84 = (lower_bound.iloc[0]['坐標-Y-WGS84'], lower_bound.iloc[0]['坐標-X-WGS84'])
    coords_upper_wgs84 = (upper_bound.iloc[0]['坐標-Y-WGS84'], upper_bound.iloc[0]['坐標-X-WGS84'])
    
    coords_lower_twd97 = (lower_bound.iloc[0]['坐標-Y-TWD97'], lower_bound.iloc[0]['坐標-X-TWD97'])
    coords_upper_twd97 = (upper_bound.iloc[0]['坐標-Y-TWD97'], upper_bound.iloc[0]['坐標-X-TWD97'])
    
    proportion = (stake_number - lower_stake) / (upper_stake - lower_stake)
    
    lat_wgs84 = coords_lower_wgs84[0] + proportion * (coords_upper_wgs84[0] - coords_lower_wgs84[0])
    lon_wgs84 = coords_lower_wgs84[1] + proportion * (coords_upper_wgs84[1] - coords_lower_wgs84[1])
    
    lat_twd97 = coords_lower_twd97[0] + proportion * (coords_upper_twd97[0] - coords_lower_twd97[0])
    lon_twd97 = coords_lower_twd97[1] + proportion * (coords_upper_twd97[1] - coords_lower_twd97[1])
    
    return (lon_twd97, lat_twd97), (lon_wgs84, lat_wgs84)

def query_coordinates():
    input_text = entry_input.get("1.0", tk.END).strip()
    if not input_text:
        messagebox.showerror("輸入錯誤", "請輸入省道公路編號與里程樁號")
        return
    
    lines = input_text.split("\n")
    results = []
    for line in lines:
        if not line.strip():
            continue
        parts = line.split()
        if len(parts) != 2:
            messagebox.showerror("輸入錯誤", f"格式錯誤：{line}")
            return
        road_number, stake_number = parts[0], float(parts[1])
        twd97_coords, wgs84_coords = get_coordinates(road_number, stake_number)
        if twd97_coords and wgs84_coords:
            results.append(f"{road_number} {stake_number}:\n  TWD97: X={twd97_coords[0]}, Y={twd97_coords[1]}\n  WGS84: X={wgs84_coords[0]}, Y={wgs84_coords[1]}\n")
        elif wgs84_coords:
            results.append(f"{road_number} {stake_number} (插值計算):\n  TWD97: X={twd97_coords[0]}, Y={twd97_coords[1]}\n  WGS84: X={wgs84_coords[0]}, Y={wgs84_coords[1]}\n")
        else:
            results.append(f"{road_number} {stake_number}: 無法找到對應的樁號或進行插值計算。\n")
    
    text_output.delete("1.0", tk.END)
    text_output.insert(tk.END, "\n".join(results))

# 建立主窗口
root = tk.Tk()
root.title("省道公路樁號轉換坐標程式")

# 標題
label_title = tk.Label(root, text="省道公路樁號轉換坐標程式", font=("Arial", 16))
label_title.pack(pady=10)

# 輸入說明
frame_input = tk.Frame(root)
label_instruction = tk.Label(frame_input, text="請輸入省道公路編號與里程樁號", font=("Arial", 12))
label_example = tk.Label(frame_input, text="範例：\n台1 11.1\n台2 12.3", font=("Arial", 10), justify=tk.LEFT)
label_instruction.grid(row=0, column=0, sticky='w')
label_example.grid(row=1, column=0, sticky='w')

# 輸入框
entry_input = tk.Text(frame_input, height=10, width=50)
entry_input.grid(row=2, column=0, pady=5)

# 送出按鈕
button_submit = tk.Button(frame_input, text="送出", command=query_coordinates)
button_submit.grid(row=3, column=0, pady=5)

# 加載和顯示圖片
logo_path = r'C:\00_Python\06_coordinate_lookup\Ver1.0_logo.bmp'
logo_image = Image.open(logo_path)

# 縮小圖片50%
width, height = logo_image.size
logo_image = logo_image.resize((width // 2, height // 2), Image.LANCZOS)

logo_photo = ImageTk.PhotoImage(logo_image)
label_logo = tk.Label(frame_input, image=logo_photo)
label_logo.grid(row=4, column=0, pady=5, sticky='w')

# 版本信息
label_version = tk.Label(frame_input, text="黃韋凱 製作 Ver1.0", font=("Arial", 10))
label_version.grid(row=5, column=0, pady=5, sticky='w')

frame_input.pack(side=tk.LEFT, padx=10, pady=10)

# 輸出框
frame_output = tk.Frame(root)
label_output = tk.Label(frame_output, text="WGS84坐標, TWD97坐標", font=("Arial", 12))
label_output.grid(row=0, column=0, sticky='w')

text_output = tk.Text(frame_output, height=20, width=50)
text_output.grid(row=1, column=0, pady=5)

frame_output.pack(side=tk.LEFT, padx=10, pady=10)

root.mainloop()
