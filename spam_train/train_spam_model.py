import pandas as pd
import joblib 
from sklearn.feature_extraction.text  import TfidfVectorizer
from sklearn.svm import LinearSVC
from sklearn.pipeline import Pipeline
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score, classification_report

# step1: Extract
print("dang tai file spam_email.csv ...")
try:
    df= pd.read_csv('spam_email.csv')
    df = df.dropna()

    texts = df('text')
    labels = df('spam')
    print (f" da tai thanh cong {len(texts)} email de train")

except FileNotFoundError:
    print("Loi: khong tim thay file")
    exit()

#step 2: pipeline
print("dang xay dung pipeline...   ")
#TfidfVectorizer chuyen van bang thanh vector space
model = Pipeline([
    ('tfidf', TfidfVectorizer(stop_words='english', max_df= 0.7)),
    ('clf', LinearSVC(c=1.0, dual=True)),

])

#step 3: train spam or ham
print("80% train 20% test")
X_train, X_test, y_train, y_test = train_test_split(texts, labels,test_size=0.2, random_state= 42, stratify=True)
print("dang train mo hinh")
model.fit(X_train, y_train)
# danh gia mo hinh
y_pred = model.predict(X_test)
accuracy = accuracy_score(y_test, y_pred)
print(f"Accuracy = {accuracy * 100:.2f} %")
print(classification_report(y_test, y_pred))
# luu mo hinh
print("luu mo hinh vao 'spam_model.pkl'...")
joblib.dump(model,'spam_model.pkl')
print("DONEEEE, file da san sang su dung")

