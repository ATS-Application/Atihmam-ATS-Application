import axiosClient from "./axiosClient";

export const login = (email, password) =>
  axiosClient.post("/auth/login", { email, password });

export const register = (email, password, full_name) =>
  axiosClient.post("/auth/register", { email, password, full_name });