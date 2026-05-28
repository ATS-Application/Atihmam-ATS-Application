import { forgotPassword } from "../api/authApi";

export function useForgotPassword() {
  return useMutation({
    mutationFn: (email) => forgotPassword(email),
  });
}