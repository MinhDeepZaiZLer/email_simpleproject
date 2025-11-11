import pandas as pd
import joblib 
import re  # <-- Thêm thư viện Regex
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.svm import LinearSVC
from sklearn.pipeline import Pipeline
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score, classification_report

# --- [MỚI] Hàm dọn dẹp văn bản ---
def clean_text(text):
    """Hàm dọn dẹp văn bản thô"""
    text = str(text).lower() # Chuyển sang chữ thường
    # text = re.sub(r'subject:', '', text, flags=re.IGNORECASE) # <-- XÓA DÒNG NÀY
    text = re.sub(r'http\S+|www\S+', ' ', text) # Xóa URLs
    text = re.sub(r'\S+@\S+', ' ', text) # Xóa email
    text = re.sub(r'[\d\W_]+', ' ', text) # Xóa số, ký tự đặc biệt, dấu '_'
    text = re.sub(r'\s+', ' ', text).strip() # Xóa khoảng trắng thừa
    return text

# --- Step 1: Extract và Dọn Dẹp ---
print("Dang tai file spam_email.csv ...")
try:
    df = pd.read_csv('D:\\mail\\email_simpleproject\\spam_train\\spam_email.csv')
    df = df.dropna()

    # [THAY ĐỔI QUAN TRỌNG] Áp dụng hàm dọn dẹp
    print("Dang lam sach du lieu train...")
    texts = df['text'].apply(clean_text) 
    
    labels = df['spam']
    print (f"Da tai thanh cong va lam sach {len(texts)} email de train")

except FileNotFoundError:
    print("Loi: khong tim thay file")
    exit()
except KeyError as e:
    print(f"Loi: Khong tim thay cot trong CSV. Can cot 'text' va 'spam'. Error: {e}")
    exit()


# --- Step 2: Pipeline ---
print("dang xay dung pipeline...   ")
# TfidfVectorizer chuyen van bang thanh vector space
model = Pipeline([
    ('tfidf', TfidfVectorizer(stop_words='english', max_df=0.7)),
    ('clf', LinearSVC(C=1.0, dual=True, class_weight='balanced', max_iter=2000)),
])


# --- Step 3: Train và Đánh giá ---
print("80% train 20% test")
X_train, X_test, y_train, y_test = train_test_split(texts, labels, test_size=0.2, random_state=42, stratify=labels)

print("Dang train mo hinh...")
model.fit(X_train, y_train)

print("\n--- Danh gia mo hinh ---")
y_pred = model.predict(X_test)
accuracy = accuracy_score(y_test, y_pred)
print(f"Accuracy = {accuracy * 100:.2f} %")
print(classification_report(y_test, y_pred))


# --- Step 4: Luu mo hinh ---
print("\nLuu mo hinh vao 'spam_model.pkl'...")
joblib.dump(model,'spam_model.pkl')
print("DONEEEE, file da san sang su dung")