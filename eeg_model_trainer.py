"""
EEG Model Trainer
Trains a machine learning model from collected training data
"""

import pandas as pd
import numpy as np
import pickle
from datetime import datetime
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split, cross_val_score
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import classification_report, confusion_matrix
import matplotlib.pyplot as plt
import seaborn as sns
from pathlib import Path

print("="*70)
print("🧠 EEG Model Trainer")
print("="*70)

# Find most recent training data file
def find_latest_training_file():
    """Find the most recent training data CSV file"""
    files = list(Path('.').glob('eeg_training_*.csv'))
    if not files:
        return None
    # Sort by modification time, return most recent
    latest = max(files, key=lambda f: f.stat().st_mtime)
    return str(latest)

# Load data
csv_file = find_latest_training_file()

if csv_file is None:
    print("❌ No training data found!")
    print("💡 Please run eeg_training_collector.py first to collect data")
    exit(1)

print(f"📂 Loading training data: {csv_file}")
df = pd.read_csv(csv_file)

print(f"✅ Loaded {len(df)} samples")
print(f"\n📊 Data Overview:")
print(df.head())

# Check data distribution
print(f"\n🎯 Direction Distribution:")
print(df['direction'].value_counts())

# Filter out poor signal quality samples
original_count = len(df)
df = df[df['signal_quality'] < 100]  # Keep only good quality samples
filtered_count = len(df)
print(f"\n🔍 Filtered samples: {original_count} → {filtered_count} (removed {original_count - filtered_count} poor quality)")

if len(df) < 50:
    print("⚠️ WARNING: Very few samples! Model may not be accurate.")
    print("💡 Collect more training data for better results")

# Prepare features and labels
print("\n🔧 Preparing features...")

# Feature columns
feature_columns = [
    'attention', 'meditation', 'raw',
    'delta', 'theta', 
    'low_alpha', 'high_alpha',
    'low_beta', 'high_beta',
    'low_gamma', 'mid_gamma'
]

X = df[feature_columns].values
y = df['direction'].values

print(f"Features shape: {X.shape}")
print(f"Labels shape: {y.shape}")

# Feature engineering - add derived features
print("\n🧮 Engineering advanced features & Signal Smoothing...")

# 1. Signal Averaging (Smoothing) 
# We apply a rolling average to reduce noise if there are sequential samples
df_sorted = df.sort_values(['direction', 'timestamp'])
for col in feature_columns:
    # 3-point rolling average within the same direction group
    df[col] = df_sorted.groupby('direction')[col].transform(lambda x: x.rolling(window=3, min_periods=1).mean())

# 2. Advanced Ratio Engineering
# These ratios are standard in EEG research for identifying mental states
alpha_sum = df['low_alpha'] + df['high_alpha']
beta_sum = df['low_beta'] + df['high_beta']
gamma_sum = df['low_gamma'] + df['mid_gamma']
theta = df['theta']
delta = df['delta']

# Add ratio features
df['alpha_theta_ratio'] = alpha_sum / (theta + 1)
df['beta_alpha_ratio'] = beta_sum / (alpha_sum + 1)
df['beta_theta_ratio'] = beta_sum / (theta + 1)      # Focus/Arousal index
df['gamma_beta_ratio'] = gamma_sum / (beta_sum + 1) # Peak concentration
df['gamma_alpha_ratio'] = gamma_sum / (alpha_sum + 1)
df['engagement_ratio'] = df['attention'] / (df['meditation'] + 1)
df['focus_index'] = beta_sum / (alpha_sum + theta + 1)
df['stress_index'] = df['high_beta'] / (df['low_alpha'] + 1)

# List of all feature names for the model
all_features = feature_columns + [
    'alpha_theta_ratio', 'beta_alpha_ratio', 'beta_theta_ratio',
    'gamma_beta_ratio', 'gamma_alpha_ratio',
    'engagement_ratio', 'focus_index', 'stress_index'
]

X_engineered = df[all_features].values
print(f"Enhanced features shape: {X_engineered.shape}")

# Split data into training and testing sets
print("\n📊 Splitting data (80% train, 20% test)...")
X_train, X_test, y_train, y_test = train_test_split(
    X_engineered, y, test_size=0.2, random_state=42, stratify=y
)

print(f"Training samples: {len(X_train)}")
print(f"Testing samples: {len(X_test)}")

# Standardize features (important for ML models)
print("\n⚖️ Standardizing features...")
scaler = StandardScaler()
X_train_scaled = scaler.fit_transform(X_train)
X_test_scaled = scaler.transform(X_test)

# Train Random Forest Classifier
print("\n🌲 Training Random Forest Classifier...")
model = RandomForestClassifier(
    n_estimators=300,      
    max_depth=25,          
    min_samples_split=4,
    min_samples_leaf=1,
    class_weight='balanced', # Crucial for handling 'CLICK' and 'IDLE' samples
    random_state=42,
    n_jobs=-1              
)

model.fit(X_train_scaled, y_train)
print("✅ Model trained with Signal Averaging and Balanced Weights!")

# Evaluate model
print("\n📈 Evaluating model...")

# Training accuracy
train_score = model.score(X_train_scaled, y_train)
print(f"Training Accuracy: {train_score*100:.2f}%")

# Testing accuracy
test_score = model.score(X_test_scaled, y_test)
print(f"Testing Accuracy: {test_score*100:.2f}%")

# Cross-validation score
cv_scores = cross_val_score(model, X_train_scaled, y_train, cv=5)
print(f"Cross-Validation Accuracy: {cv_scores.mean()*100:.2f}% (+/- {cv_scores.std()*2*100:.2f}%)")

# Detailed classification report
print("\n📋 Detailed Classification Report:")
y_pred = model.predict(X_test_scaled)
print(classification_report(y_test, y_pred))

# Feature importance
print("\n🎯 Feature Importance (Top 10):")
feature_importance = pd.DataFrame({
    'feature': all_features,
    'importance': model.feature_importances_
}).sort_values('importance', ascending=False)

print(feature_importance.head(10).to_string(index=False))

# Visualizations
print("\n📊 Generating visualizations...")

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

# Save visualization
viz_filename = f"model_evaluation_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
plt.savefig(viz_filename, dpi=150, bbox_inches='tight')
print(f"✅ Saved visualization: {viz_filename}")

plt.show()

# Save model and scaler
print("\n💾 Saving trained model...")
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

print(f"✅ Model saved: {model_filename}")

# Prediction example
print("\n🔮 Testing prediction on a random sample:")
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
print("🎉 TRAINING COMPLETE!")
print("="*70)
print(f"📊 Model Performance:")
print(f"   Training Accuracy:   {train_score*100:.2f}%")
print(f"   Testing Accuracy:    {test_score*100:.2f}%")
print(f"   Cross-Val Accuracy:  {cv_scores.mean()*100:.2f}%")
print(f"\n📁 Files Created:")
print(f"   Model: {model_filename}")
print(f"   Visualization: {viz_filename}")
print(f"\n💡 Next Steps:")
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