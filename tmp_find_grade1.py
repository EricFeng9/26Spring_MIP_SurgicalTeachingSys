import math
import sys
sys.path.append(r"c:\Users\21333\Documents\GitHub\26Spring_MIP_SurgicalTeachingSys\simulation_test")
import laser_simulator_bright_warm_v2 as m

model = m.LaserPhysicalModel({"power":100.0,"spot_size":100.0,"exposure_time":100.0,"wavelength":532.0})
print("tau0,tau1,tau2:", model.tau_0, model.tau_1, model.tau_2)

# check the user sample
z0,g0 = model.compute_z_and_grade(50.0,400.0,10.0,532.0)
print("sample P50 S400 T10 -> z,grade:", z0, g0)

# find some grade-1 combinations in UI integer ranges for 532nm
found=[]
for P in range(50,401):
    for S in range(50,401):
        for T in range(10,501):
            z,g = model.compute_z_and_grade(float(P),float(S),float(T),532.0)
            if g==1 and z>=0.2:  # actually visible grade-1
                found.append((P,S,T,z))
                if len(found)>=12:
                    break
        if len(found)>=12:
            break
    if len(found)>=12:
        break

print("first 12 visible grade1 combos:")
for item in found:
    print(item)
