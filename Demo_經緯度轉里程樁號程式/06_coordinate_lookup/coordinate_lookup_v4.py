import tkinter as tk
from tkinter import messagebox
from PIL import Image, ImageTk
import pandas as pd
from geopy.distance import geodesic
import os

# Get the directory where the script is located
script_dir = os.path.dirname(os.path.abspath(__file__))
data_file_path = os.path.join(script_dir, '(11307)14省道公路路線里程牌(指45)KMZ.csv')

# 讀取數據
data = pd.read_csv(data_file_path)
data['牌面內容'] = data['牌面內容'].astype(str).str.replace('K', '').astype(float)

# 根據省道公路編號與里程樁號獲取坐標
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

# 插值計算坐標
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

# 根據經緯度或TWD97二度分帶座標反向查找最近的里程樁號
def get_nearest_stake_number(latitude=None, longitude=None, twd97_x=None, twd97_y=None):
    if latitude is not None and longitude is not None:
        def distance(row):
            return geodesic((latitude, longitude), (row['坐標-Y-WGS84'], row['坐標-X-WGS84'])).meters
    elif twd97_x is not None and twd97_y is not None:
        def distance(row):
            return ((row['坐標-X-TWD97'] - twd97_x) ** 2 + (row['坐標-Y-TWD97'] - twd97_y) ** 0.5)
    else:
        return None, None
    
    data['距離'] = data.apply(distance, axis=1)
    nearest_row = data.loc[data['距離'].idxmin()]
    
    return nearest_row['公路編號'], nearest_row['牌面內容']

# 查詢坐標功能
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

# 查詢里程樁號功能
def query_stake_number():
    try:
        if entry_latitude.get() and entry_longitude.get():
            latitude = float(entry_latitude.get())
            longitude = float(entry_longitude.get())
            road_number, stake_number = get_nearest_stake_number(latitude=latitude, longitude=longitude)
        elif entry_twd97_x.get() and entry_twd97_y.get():
            twd97_x = float(entry_twd97_x.get())
            twd97_y = float(entry_twd97_y.get())
            road_number, stake_number = get_nearest_stake_number(twd97_x=twd97_x, twd97_y=twd97_y)
        else:
            messagebox.showerror("輸入錯誤", "請輸入有效的經緯度或TWD97二度分帶座標")
            return
    except ValueError:
        messagebox.showerror("輸入錯誤", "請輸入有效的數值")
        return
    
    if road_number and stake_number:
        result_text = f"最近的里程樁號：\n  公路編號: {road_number}\n  里程樁號: {stake_number}\n"
    else:
        result_text = "無法找到對應的里程樁號。"
    
    text_output.delete("1.0", tk.END)
    text_output.insert(tk.END, result_text)

# 建立主窗口
root = tk.Tk()
root.title("省道公路樁號轉換坐標程式")

# 主框架
frame_main = tk.Frame(root)
frame_main.pack(padx=10, pady=10)

# 左側框架（輸入）
frame_input = tk.Frame(frame_main)
frame_input.grid(row=0, column=0, padx=10, pady=10, sticky="n")

label_instruction = tk.Label(frame_input, text="請輸入省道公路編號與里程樁號", font=("Arial", 12))
label_instruction.pack(anchor="w")

label_example = tk.Label(frame_input, text="範例：\n台1 11.1\n台2丁 2.3\n台29臨11 7.5", font=("Arial", 10), justify=tk.LEFT)
label_example.pack(anchor="w")

entry_input = tk.Text(frame_input, height=10, width=40)
entry_input.pack(pady=5)

button_submit = tk.Button(frame_input, text="送出", command=query_coordinates)
button_submit.pack(pady=5)

# 經緯度與TWD97輸入框
label_latitude = tk.Label(frame_input, text="請輸入緯度 (WGS84):", font=("Arial", 10))
label_latitude.pack(anchor="w")
entry_latitude = tk.Entry(frame_input)
entry_latitude.pack(pady=5)

label_longitude = tk.Label(frame_input, text="請輸入經度 (WGS84):", font=("Arial", 10))
label_longitude.pack(anchor="w")
entry_longitude = tk.Entry(frame_input)
entry_longitude.pack(pady=5)

label_twd97_x = tk.Label(frame_input, text="請輸入TWD97二度分帶 X:", font=("Arial", 10))
label_twd97_x.pack(anchor="w")
entry_twd97_x = tk.Entry(frame_input)
entry_twd97_x.pack(pady=5)

label_twd97_y = tk.Label(frame_input, text="請輸入TWD97二度分帶 Y:", font=("Arial", 10))
label_twd97_y.pack(anchor="w")
entry_twd97_y = tk.Entry(frame_input)
entry_twd97_y.pack(pady=5)

button_query_stake = tk.Button(frame_input, text="查詢最近里程樁號", command=query_stake_number)
button_query_stake.pack(pady=10)

# 右側框架（輸出）
frame_output = tk.Frame(frame_main)
frame_output.grid(row=0, column=1, padx=10, pady=10, sticky="n")

label_output = tk.Label(frame_output, text="省道樁號查找坐標或反向查找結果", font=("Arial", 12))
label_output.pack(anchor="w")

text_output = tk.Text(frame_output, height=20, width=50)
text_output.pack(pady=5)

# 圖片與版本號框架，與輸入框底部對齊
frame_bottom = tk.Frame(frame_main)
frame_bottom.grid(row=1, column=0, padx=10, pady=10, columnspan=2)

logo_path = os.path.join(script_dir, 'Ver1.0_logo.bmp')
if os.path.exists(logo_path):
    logo_image = Image.open(logo_path)
    width, height = logo_image.size
    logo_image = logo_image.resize((width // 2, height // 2), Image.LANCZOS)
    logo_photo = ImageTk.PhotoImage(logo_image)
    label_logo = tk.Label(frame_bottom, image=logo_photo)
    label_logo.grid(row=0, column=0, padx=5, pady=5)

label_version = tk.Label(frame_bottom, text="黃韋凱 製作 Ver3.0", font=("Arial", 10))
label_version.grid(row=0, column=1, padx=5, pady=5)

root.mainloop()
