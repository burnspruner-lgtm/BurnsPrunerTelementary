def calculate_extra_metrics(metrics):
    # metrics = [rpm, speed, hp, torque, ve, fuel_rate, coolant, load, fuel_total, stability, temp_in]
    rpm = metrics[0]
    speed = metrics[1]
    fuel_rate = metrics[5]

    # 1. Instant MPG (or L/100km)
    if speed > 5 and fuel_rate > 0:
        l_100km = (fuel_rate / speed) * 100
    else:
        l_100km = 0

    # 2. Power-to-Weight (Assuming 1500kg car)
    hp_per_tonne = metrics[2] / 1.5

    return {
        "l_100km": l_100km,
        "hp_per_tonne": hp_per_tonne
    }
    