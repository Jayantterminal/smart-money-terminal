import pandas as pd
import numpy as np

def calculate_sector_flow(df_sectors):
    """
    Calculates Fortnightly / Base comparative shift for sectors.
    """
    df_sectors["Flow Shift (%)"] = (df_sectors["val_curr"] - df_sectors["val_base"]).round(2)
    
    def assign_signal(shift):
        if shift >= 2.0:
            return "🟢 Heavy Inflow"
        elif shift > 0:
            return "🟢 Inflow"
        elif shift == 0.0:
            return "⚪ Neutral"
        elif shift <= -0.5:
            return "🔴 Heavy Outflow"
        else:
            return "🔴 Outflow"

    df_sectors["Flow Signal"] = df_sectors["Flow Shift (%)"].apply(assign_signal)
    return df_sectors.sort_values(by="Flow Shift (%)", ascending=False).reset_index(drop=True)

def detect_silent_accumulation(df_stocks):
    """
    Detects stocks showing relative strength / silent accumulation 
    when the broader market or sector is flat/weak.
    """
    # Rule: Low/Negative sector change but positive/tight stock range with volume buildup
    accumulating_stocks = []
    for _, row in df_stocks.iterrows():
        if row['Stock_Change (%)'] >= -0.5 and row['Delivery (%)'] >= 60.0:
            status = "🟢 Silent Accumulation (Smart Money)"
        elif row['Stock_Change (%)'] > 2.0:
            status = "🟢 Active Markup"
        else:
            status = "⚪ Normal / Watching"
        accumulating_stocks.append(status)
        
    df_stocks["Accumulation Status"] = accumulating_stocks
    return df_stocks
