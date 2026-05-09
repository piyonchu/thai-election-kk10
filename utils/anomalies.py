import pandas as pd
import numpy as np
from scipy.stats import zscore, chisquare
from sklearn.ensemble import IsolationForest

def check_ballot_reconciliation(df_units):
    """
    Refined ballot reconciliation that filters out empty/NaN clerical errors 
    from actual mathematical impossibilities (Fraud).
    """
    df = df_units.copy()
    
    # 1. Flag Clerical Errors (Missing Data)
    clerical_mask = df[['Voters_Showed_Up', 'Used_Ballots', 'Valid_Ballots']].isna().any(axis=1) | (df['Voters_Showed_Up'] == 0)
    
    # Process only rows that have actual numerical data
    df_clean = df[~clerical_mask].copy()
    
    # 2. Flag Mathematical Fraud
    ghost_voting = df_clean['Used_Ballots'] > df_clean['Voters_Showed_Up']
    math_mismatch = df_clean['Used_Ballots'] != (df_clean['Valid_Ballots'] + df_clean['Invalid_Ballots'] + df_clean['No_Vote_Ballots'])
    over_100_turnout = df_clean['Turnout_Pct'] > 100

    df_clean['Anomaly_Type'] = ""
    df_clean.loc[ghost_voting, 'Anomaly_Type'] += "Ghost Voters; "
    df_clean.loc[math_mismatch, 'Anomaly_Type'] += "Math Mismatch; "
    df_clean.loc[over_100_turnout, 'Anomaly_Type'] += "Turnout > 100%; "
    
    failed_units = df_clean[df_clean['Anomaly_Type'] != ""]
    clerical_units = df[clerical_mask].copy()
    clerical_units['Anomaly_Type'] = "Missing/Zero Data (Clerical)"
    
    return failed_units[['Unit_ID', 'District', 'Subdistrict', 'Voters_Showed_Up', 'Used_Ballots', 'Anomaly_Type']], clerical_units[['Unit_ID', 'District', 'Subdistrict', 'Voters_Showed_Up', 'Used_Ballots', 'Anomaly_Type']]

def calculate_isolation_forest(df_units):
    """
    Advanced Multivariate Anomaly Detection using Machine Learning.
    Evaluates Turnout, Invalid Ballot Rate, and No Vote Rate simultaneously.
    """
    df = df_units.dropna(subset=['Turnout_Pct', 'Invalid_Pct', 'No_Vote_Ballots']).copy()
    
    # Calculate No Vote Percentage
    df['No_Vote_Pct'] = (df['No_Vote_Ballots'] / df['Used_Ballots']) * 100
    df['No_Vote_Pct'].fillna(0, inplace=True)
    
    # Select features for the model
    features = ['Turnout_Pct', 'Invalid_Pct', 'No_Vote_Pct']
    X = df[features]
    
    # Train Isolation Forest (contamination = 0.02 assumes ~2% of units might be anomalous)
    clf = IsolationForest(n_estimators=100, contamination=0.02, random_state=42)
    df['Anomaly_Score'] = clf.fit_predict(X)
    df['Anomaly_Severity'] = clf.decision_function(X) # Lower score = more anomalous
    
    # Filter for anomalies (Score == -1)
    anomalies = df[df['Anomaly_Score'] == -1].sort_values(by='Anomaly_Severity')
    
    return anomalies[['Unit_ID', 'Subdistrict', 'Turnout_Pct', 'Invalid_Pct', 'No_Vote_Pct', 'Anomaly_Severity']]

def detect_symmetric_vote_buying(df_scores, candidate_target_number):
    """
    Detects the 'Double-X' vote-buying effect.
    Looks for localized, statistically impossible spikes for a specific Party List Number
    that matches the local Constituency Candidate's Number.
    """
    # Filter scores for the specific suspected party number
    target_scores = df_scores[df_scores['Party_Number'] == candidate_target_number].copy()
    
    if target_scores.empty:
        return pd.DataFrame()
        
    # Calculate the mean and standard deviation of this party's vote across the WHOLE constituency
    mean_score = target_scores['Score'].mean()
    std_score = target_scores['Score'].std()
    
    # Calculate Z-Score for this specific party's performance in each unit
    target_scores['Party_Spike_Z_Score'] = (target_scores['Score'] - mean_score) / std_score
    
    # Flag units where this random party suddenly received an massive surge of votes (Z > 3)
    suspicious_units = target_scores[target_scores['Party_Spike_Z_Score'] > 3].sort_values(by='Score', ascending=False)
    
    return suspicious_units[['Unit_ID', 'Party_Name', 'Party_Number', 'Score', 'Party_Spike_Z_Score']]


def calculate_turnout_zscores(df_units):
    """
    Calculates the Z-Score for voter turnout to find statistical outliers.
    """
    df = df_units.dropna(subset=['Turnout_Pct']).copy()
    df['Turnout_Z_Score'] = zscore(df['Turnout_Pct'])
    
    # Filter for standard deviation > 3 (extreme outliers)
    outliers = df[df['Turnout_Z_Score'].abs() > 3]
    return outliers.sort_values(by='Turnout_Z_Score', ascending=False)

def calculate_benfords_law(df_scores):
    """
    Applies Benford's Law to the first digit of every valid party score.
    """
    # Filter out 0 scores as they do not have a leading digit 1-9
    valid_scores = df_scores[df_scores['Score'] > 0].copy()
    
    # Extract the first digit as an integer
    valid_scores['First_Digit'] = valid_scores['Score'].astype(str).str[0].astype(int)
    
    # Calculate observed frequencies
    observed_counts = valid_scores['First_Digit'].value_counts().sort_index()
    total_scores = observed_counts.sum()
    observed_pct = (observed_counts / total_scores) * 100
    
    # Calculate expected frequencies using Benford's formula
    digits = np.arange(1, 10)
    expected_pct = np.log10(1 + 1/digits) * 100
    
    results = pd.DataFrame({
        'Digit': digits,
        'Expected_Pct': expected_pct,
        'Observed_Pct': observed_pct.reindex(digits, fill_value=0)
    })
    
    # Calculate Chi-Square P-Value to determine statistical significance
    expected_counts = (expected_pct / 100) * total_scores
    chi2_stat, p_val = chisquare(f_obs=observed_counts.reindex(digits, fill_value=0), f_exp=expected_counts)
    
    return results, p_val

