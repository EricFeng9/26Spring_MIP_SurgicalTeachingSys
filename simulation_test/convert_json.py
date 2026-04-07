import json
import os

# 1. 填入你的旧文件路径
input_file = r"C:\Users\21333\Documents\GitHub\26Spring_MIP_SurgicalTeachingSys\simulation_test\export_20260403_190846.json"
output_file = input_file.replace(".json", "_converted.json")

if not os.path.exists(input_file):
    print(f"找不到文件: {input_file}")
    exit()

# 2. 读取旧数据
with open(input_file, 'r', encoding='utf-8') as f:
    old_data = json.load(f)

# 获取全局的标准参数，用来给这 80 多个点“上色”
gt_params = old_data.get("ground_truth_parameters", {})
power = gt_params.get("power", 200.0)
spot_size = gt_params.get("spot_size", 200.0)
exposure_time = gt_params.get("exposure_time", 100.0)
wavelength = gt_params.get("wavelength", 532.0)

# 获取你辛辛苦苦点的坐标列表
coordinates = old_data.get("target_coordinates", [])

# 3. 组装新格式基础结构
new_data = {
    "session_id": "SESS_20260403_001",
    "_session_id": "会话唯一ID",
    "task_id": old_data.get("task_id", "T001_RP_Standard"),
    "_task_id": "对应题目ID",
    "player_info": {
        "id": "ST_007",
        "name": "张三"
    },
    "shots": []
}

# 4. 遍历并清洗每一枪的数据
for index, pos in enumerate(coordinates):
    shot_data = {
        "id": index + 1,
        "pos": pos
    }
    
    # 仅在首个记录注入注释字段
    if index == 0:
        shot_data["_pos"] = "光斑中心点坐标[x,y]"
        
    shot_data["is_trial"] = False  # 默认转为非试打点
    
    if index == 0:
        shot_data["_is_trial"] = "是否为试打点"
        
    params_data = {
        "power": power
    }
    if index == 0: params_data["_power"] = "实际功率(mW)"
    
    params_data["spot_size"] = spot_size
    if index == 0: params_data["_spot_size"] = "实际大小(um)"
    
    params_data["exposure_time"] = exposure_time
    if index == 0: params_data["_exposure_time"] = "实际曝光时间(ms)"
    
    params_data["wavelength"] = wavelength
    if index == 0: params_data["_wavelength"] = "实际波长(nm)"
    
    shot_data["params"] = params_data
    new_data["shots"].append(shot_data)

# 5. 导出新文件
with open(output_file, 'w', encoding='utf-8') as f:
    json.dump(new_data, f, indent=2, ensure_ascii=False)

print(f"转换成功！\n共成功抢救了 {len(new_data['shots'])} 个光斑坐标。\n新文件已保存至: {output_file}")