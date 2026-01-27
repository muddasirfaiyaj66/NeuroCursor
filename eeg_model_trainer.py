"""
EEG Model Trainer
Trains a machine learning model from collected training data
"""

import pandas as pd
import numpy as np
import pickle
from datetime import datetime
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split, cross_val_score, GridSearchCV
from sklearn.preprocessing import StandardScaler, LabelEncoder
# Label encoding for XGBoost
from sklearn.metrics import classification_report, confusion_matrix
import matplotlib.pyplot as plt
import seaborn as sns
from pathlib import Path

print("="*70)
print("EEG Model Trainer")
print("="*70)

# Find most recent training data file
def find_latest_training_file():
    """Find the most recent training data CSV file"""
    files = list(Path('.').glob('eeg_training_*.csv'))
    files += list(Path('.').glob('merged_training_*.csv'))
    if not files:
        return None
    # Sort by modification time, return most recent
    latest = max(files, key=lambda f: f.stat().st_mtime)
    return str(latest)

# Load data
csv_file = find_latest_training_file()

if csv_file is None:
    print("X No training data found!")
    print("! Please run eeg_training_collector.py first to collect data")
    exit(1)

print(f"Loading training data: {csv_file}")
df = pd.read_csv(csv_file)

print(f"Loaded {len(df)} samples")
print(f"\nData Overview:")
print(df.head())

# Check data distribution
print(f"\nDirection Distribution:")
print(df['direction'].value_counts())

# Filter out poor signal quality samples
original_count = len(df)
df = df[df['signal_quality'] < 100]  # Keep only good quality samples
filtered_count = len(df)
print(f"\nFiltered samples: {original_count} -> {filtered_count} (removed {original_count - filtered_count} poor quality)")

if len(df) < 50:
    print("! WARNING: Very few samples! Model may not be accurate.")
    print("! Collect more training data for better results")

# Prepare features and labels
print("\nPreparing features...")

# Feature columns
# Feature columns - Reduced to the minimum effective set for TGAM
feature_columns = [
    'attention', 'meditation',
    'theta', 
    'low_alpha', 'high_alpha',
    'low_beta', 'high_beta'
]

X = df[feature_columns].values
y = df['direction'].values

print(f"Features shape: {X.shape}")
print(f"Labels shape: {y.shape}")

# Feature engineering - add derived features
print("\nEngineering advanced features & Signal Smoothing...")

# 1. Temporal Smoothing (Rolling Average) - CAUSAL logic
# Sort globally by timestamp to maintain chronological order
df = df.sort_values('timestamp').reset_index(drop=True)

for col in feature_columns:
    # 3-point rolling average within the same direction group
    # groupby maintains the relative order of the original dataframe within each group
    df[col] = df.groupby('direction', sort=False)[col].transform(lambda x: x.rolling(window=3, min_periods=1).mean())

# 2. Minimum Effective Ratios
# ... same logic as before ...
alpha_sum = df['low_alpha'] + df['high_alpha']
beta_sum = df['low_beta'] + df['high_beta']
theta = df['theta']

df['alpha_theta_ratio'] = alpha_sum / (theta + 1)
df['beta_alpha_ratio'] = beta_sum / (alpha_sum + 1)
df['beta_theta_ratio'] = beta_sum / (theta + 1)
df['engagement_ratio'] = df['attention'] / (df['meditation'] + 1)

all_features = feature_columns + [
    'alpha_theta_ratio', 'beta_alpha_ratio', 'beta_theta_ratio',
    'engagement_ratio'
]

# Split data - Stratified split to handle block-wise collection
# (Ensures all classes are present in both train and test)
print("\nSplitting data (80% train, 20% test, stratified)...")
X_train, X_test, y_train, y_test = train_test_split(
    df[all_features].values, 
    df['direction'].values, 
    test_size=0.2, 
    random_state=42, 
    stratify=df['direction'].values
)

print(f"Training samples: {len(X_train)} (Classes: {len(np.unique(y_train))})")
print(f"Testing samples: {len(X_test)} (Classes: {len(np.unique(y_test))})")

# Standardize features (important for ML models)
print("\nStandardizing features...")
scaler = StandardScaler()
X_train_scaled = scaler.fit_transform(X_train)
X_test_scaled = scaler.transform(X_test)

# Train Random Forest Classifier
print("\nTraining Random Forest with reasonable defaults...")
model = RandomForestClassifier(
    n_estimators=100,
    max_depth=10,
    min_samples_split=4,
    class_weight='balanced',
    random_state=42,
    n_jobs=-1
)
model.fit(X_train_scaled, y_train)

# Evaluate model
print("\nEvaluating model...")

# TimeSeriesSplit Validation
# TimeSeriesSplit Validation
# Initial scores
train_score = model.score(X_train_scaled, y_train)
test_score = model.score(X_test_scaled, y_test)
from sklearn.model_selection import TimeSeriesSplit, KFold
cv = KFold(n_splits=3, shuffle=True, random_state=42)
cv_scores = cross_val_score(model, X_train_scaled, y_train, cv=cv)

print(f"Training Accuracy: {train_score*100:.2f}%")
print(f"Testing Accuracy: {test_score*100:.2f}%")
print(f"Cross-Validation Accuracy: {cv_scores.mean()*100:.2f}%")

# Detailed classification report
print("\nDetailed Classification Report:")
y_pred = model.predict(X_test_scaled)
print(classification_report(y_test, y_pred))

# Feature importance
print("\nFeature Importance (Top 10):")
feature_importance = pd.DataFrame({
    'feature': all_features,
    'importance': model.feature_importances_
}).sort_values('importance', ascending=False)

print(feature_importance.head(10).to_string(index=False))

# Visualizations
print("\nGenerating visualizations...")

# Create figure with subplots
fig = plt.figure(figsize=(15, 10))

# 1. Confusion Matrix
ax1 = plt.subplot(2, 2, 1)
cm = confusion_matrix(y_test, y_pred)
sns.heatmap(cm, annot=True, fmt='d', cmap='Blues', 
            xticklabels=model.classes_, yticklabels=model.classes_)
ax1.set_title('Confusion Matrix')
ax1.set_ylabel('True Label')
ax1.set_xlabel('Predicted Label')

# 2. Feature Importance
ax2 = plt.subplot(2, 2, 2)
top_features = feature_importance.head(10)
ax2.barh(top_features['feature'], top_features['importance'], color='steelblue')
ax2.set_xlabel('Importance')
ax2.set_title('Top 10 Feature Importance')
ax2.invert_yaxis()

# 3. Direction Distribution
ax3 = plt.subplot(2, 2, 3)
df['direction'].value_counts().plot(kind='bar', color='coral', ax=ax3)
ax3.set_title('Training Data Distribution')
ax3.set_xlabel('Direction')
ax3.set_ylabel('Count')
ax3.tick_params(axis='x', rotation=45)

# 4. Accuracy Comparison
ax4 = plt.subplot(2, 2, 4)
accuracies = ['Training', 'Testing', 'Cross-Val']
scores = [train_score, test_score, cv_scores.mean()]
bars = ax4.bar(accuracies, scores, color=['green', 'blue', 'orange'])
ax4.set_ylim([0, 1])
ax4.set_ylabel('Accuracy')
ax4.set_title('Model Performance')
ax4.axhline(y=0.8, color='r', linestyle='--', label='80% threshold')
ax4.legend()

# Add value labels on bars
for bar, score in zip(bars, scores):
    height = bar.get_height()
    ax4.text(bar.get_x() + bar.get_width()/2., height,
            f'{score*100:.1f}%', ha='center', va='bottom')

plt.tight_layout()

from sklearn.svm import SVC
# Save visualization
viz_filename = f"model_evaluation_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
plt.savefig(viz_filename, dpi=150, bbox_inches='tight')
print(f"Saved visualization: {viz_filename}")

plt.show()

# Save model and scaler
print("\n💾 Saving trained model...")
try:
    from xgboost import XGBClassifier
    xgb_installed = True
except ImportError:
    xgb_installed = False
timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
model_filename = f"eeg_model_{timestamp}.pkl"

model_package = {
    'model': model,
    'scaler': scaler,
    'feature_names': all_features,
    'classes': model.classes_,
    'train_accuracy': train_score,
    'test_accuracy': test_score,
    'cv_accuracy': cv_scores.mean(),
    'training_date': datetime.now().isoformat(),
    'training_samples': len(df)
}

with open(model_filename, 'wb') as f:
    pickle.dump(model_package, f)

# Model comparison setup (Optional but kept minimal)
models = {
    'RandomForest': model,
    'SVM': SVC(kernel='rbf', C=1.0, probability=True, class_weight='balanced', random_state=42)
}

# SVM Training
print("\nTraining SVM (RBF kernel)...")
models['SVM'].fit(X_train_scaled, y_train)

# Evaluate all models
print("\nEvaluating models with TimeSeriesSplit...")
results = {}
for name, m in models.items():
    m.fit(X_train_scaled, y_train) # Ensure fresh fit
    tr_s = m.score(X_train_scaled, y_train)
    te_s = m.score(X_test_scaled, y_test)
    cv_s = cross_val_score(m, X_train_scaled, y_train, cv=cv).mean()
    y_pred = m.predict(X_test_scaled)
    results[name] = {
        'train_score': tr_s,
        'test_score': te_s,
        'cv_score': cv_s,
        'y_pred': y_pred
    }
    print(f"\nModel: {name}")
    print(classification_report(y_test, y_pred))

# Select best model
best_model_name = max(results, key=lambda k: results[k]['test_score'])
model = models[best_model_name]
print(f"\n🏆 Best model: {best_model_name} (Test Accuracy: {results[best_model_name]['test_score']*100:.2f}%)")
print(f"✅ Model saved: {model_filename}")

# Prediction example
print("\nPrediction on a random sample:")
random_idx = np.random.randint(0, len(X_test_scaled))
sample = X_test_scaled[random_idx:random_idx+1]
prediction = model.predict(sample)[0]
probabilities = model.predict_proba(sample)[0]
true_label = y_test[random_idx]

print(f"True Direction: {true_label}")
print(f"Predicted Direction: {prediction}")
print(f"Confidence:")
for label, prob in zip(model.classes_, probabilities):
    print(f"  {label}: {prob*100:.1f}%")

# Summary
print("\n" + "="*70)
print("TRAINING COMPLETE!")
print("="*70)
print(f"Model Performance ({best_model_name}):")
print(f"   Training Accuracy:   {results[best_model_name]['train_score']*100:.2f}%")
print(f"   Testing Accuracy:    {results[best_model_name]['test_score']*100:.2f}%")
print(f"   Cross-Val Accuracy:  {results[best_model_name]['cv_score']*100:.2f}%")
print(f"\nFiles Created:")
print(f"   Model: {model_filename}")
print(f"   Visualization: {viz_filename}")
print(f"\nNext Steps:")
print(f"   1. Load this model in eeg_cursor_control.py")
print(f"   2. Select 'ML Model' mode")
print(f"   3. Click 'Load Model' and select: {model_filename}")
print(f"   4. Start controlling your cursor!")
print("="*70)

# Quality assessment
if test_score < 0.6:
    print("\n⚠️ WARNING: Low accuracy! Consider:")
    print("   - Collecting more training data")
    print("   - Ensuring consistent electrode placement")
    print("   - Training when you're alert and focused")
elif test_score < 0.75:
    print("\n✅ Decent accuracy! Model should work reasonably well.")
    print("   - Consider collecting more data for improvement")
elif test_score < 0.85:
    print("\n🎯 Good accuracy! Model should work well.")
    print("   - You can use this model for cursor control")
else:
    print("\n🌟 Excellent accuracy! Model is ready for use!")
    print("   - Great job with data collection!")

print("\n💡 Tips for better accuracy:")
print("   - Collect data at the same time of day")
print("   - Use consistent electrode placement")
print("   - Stay focused during training")
print("   - Collect 100+ samples per direction")
print("   - Ensure good signal quality (< 50)")