# Fix: Firebase Security Rules

The Firebase config object (`apiKey`, `authDomain`, `projectId`, etc.) is public by design and belongs in your frontend. It is not a secret. Do not waste time hiding it. Your security comes entirely from Security Rules. If your rules are in test mode, your database is open to the world regardless of how well you hid the config.

## Step 1: Find the current rules

Check `firestore.rules` (or Realtime Database rules) in the repo, and the Rules tab in the Firebase console. The dangerous patterns:

```
// Wide open. Anyone can read and write everything. [CRITICAL]
allow read, write: if true;

// Test mode that has not expired, or expired into open. [CRITICAL]
allow read, write: if request.time < timestamp.date(2025, 1, 1);
```

If there is no `firestore.rules` file tracked in the repo, that is a `[HIGH]`: your rules only exist in the console and cannot be reviewed or restored.

## Step 2: Write ownership rules (Firestore)

The common pattern is "a document belongs to the user in its `userId` field, or it lives under `users/{uid}/...`."

```
rules_version = '2';
service cloud.firestore {
  match /databases/{database}/documents {

    // Signed-in check
    function isSignedIn() {
      return request.auth != null;
    }

    // Documents that carry a userId field
    match /todos/{todoId} {
      allow read: if isSignedIn() && resource.data.userId == request.auth.uid;
      allow create: if isSignedIn() && request.resource.data.userId == request.auth.uid;
      allow update, delete: if isSignedIn() && resource.data.userId == request.auth.uid;
    }

    // Per-user subcollection: users/{uid}/notes/{noteId}
    match /users/{uid}/{document=**} {
      allow read, write: if isSignedIn() && request.auth.uid == uid;
    }

    // Public-read, owner-write (e.g. blog posts)
    match /posts/{postId} {
      allow read: if true;
      allow create: if isSignedIn() && request.resource.data.authorId == request.auth.uid;
      allow update, delete: if isSignedIn() && resource.data.authorId == request.auth.uid;
    }

    // Everything not matched above is denied by default. Good.
  }
}
```

Notes:
- `resource.data` is the existing document; `request.resource.data` is the incoming write. Use `request.resource` on create/update so a user cannot write a doc owned by someone else.
- Rules do not filter queries. A query that could return documents the user is not allowed to read will be rejected, not silently trimmed. Structure queries to match the rules (for example, always filter `where('userId', '==', uid)`).
- There is no "catch-all allow" at the bottom. Anything not explicitly allowed is denied. That is what you want.

## Step 3: Realtime Database equivalent

```json
{
  "rules": {
    "users": {
      "$uid": {
        ".read": "auth != null && auth.uid === $uid",
        ".write": "auth != null && auth.uid === $uid"
      }
    }
  }
}
```

## Step 4: Deploy and verify

- Commit `firestore.rules` to the repo so it is reviewable and restorable.
- Deploy: `firebase deploy --only firestore:rules`.
- Use the Rules Playground in the console to simulate a read as User A on User B's document. It must deny.
- MANUAL: signed in as User A, attempt to read User B's data from the client. Paste the permission-denied result into the audit as evidence.
