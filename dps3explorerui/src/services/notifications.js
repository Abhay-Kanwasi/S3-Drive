import { getAuthHeaders } from "@/services/auth";

const API_HOSTNAME = process.env.NEXT_PUBLIC_HOSTNAME;
const notifBase = `${API_HOSTNAME}/explorer/notifications`;

export const getNotifications = async () => {
  const response = await fetch(notifBase, {
    headers: getAuthHeaders(),
  });
  if (!response.ok) {
    const error = new Error("Failed to fetch notifications");
    error.status = response.status;
    throw error;
  }
  return response.json();
};

export const markNotificationsRead = async ({ ids, all }) => {
  const body = all ? { all: true } : { ids };
  const response = await fetch(`${notifBase}/read`, {
    method: "POST",
    headers: getAuthHeaders(),
    body: JSON.stringify(body),
  });
  if (!response.ok) throw new Error("Failed to mark notifications as read");
  return response.json();
};

export const dismissNotification = async (id) => {
  const response = await fetch(`${notifBase}/${id}`, {
    method: "DELETE",
    headers: getAuthHeaders(),
  });
  if (!response.ok) throw new Error("Failed to dismiss notification");
  return response.json();
};
