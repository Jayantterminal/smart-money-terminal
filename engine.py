import pandas as pd
import numpy as np

def sector_rotation_3_fortnights(df_history_list):
    """
    df_history_list: List of DataFrame or multi-period dataset containing 
    Fortnight 1 (Recent), Fortnight 2 (Previous), and Fortnight 3 (Older).
    """
    # 3 Fortnights ka data combine karke multi-period momentum check karne ka logic
    # Fortnight 1 (Current 15 days), Fortnight 2 (16-30 days), Fortnight 3 (31-45 days)
    
    # Base implementation for 3-Fortnight weighted shift calculation
    df_base = df_history_list[0].copy()
    
    # Weighting recent momentum higher while keeping multi-period structural shift in check
    df_base['Weighted_Flow'] = (
        (df_history_list[0]['Flow'] * 0.5) + 
        (df_history_list[1]['Flow'] * 0.3) + 
        (df_history_list[2]['Flow'] * 0.2)
    )
    
    # Quadrant mapping based on 3-period trend persistence
    def assign_quadrant(row):
        if row['Weighted_Flow'] > 1.5 and row['Flow'] > 0:
            return "Leading"
        elif row['Weighted_Flow'] > 0 and row['Flow'] > 0:
            return "Improving"
        elif row['Weighted_Flow'] < 0 and row['Flow'] < 0:
            return "Lagging"
        else:
            return "Weakening"
            
    df_base['Quadrant'] = df_base.apply(assign_quadrant, axis=1)
    return df_base.sort_values(by="Weighted_Flow", ascending=False).reset_index(drop=True)
