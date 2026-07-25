const AGENT_CHAT_URL = "http://agent:8000/chat";

export async function POST(request: Request) {
  const contentType = request.headers.get("content-type") ?? "application/json";
  const requestBody = await request.text();

  try {
    const agentResponse = await fetch(AGENT_CHAT_URL, {
      method: "POST",
      headers: {
        "Content-Type": contentType,
      },
      body: requestBody,
      cache: "no-store",
    });

    const responseBody = await agentResponse.text();
    const responseContentType =
      agentResponse.headers.get("content-type") ?? "application/json";

    return new Response(responseBody, {
      status: agentResponse.status,
      headers: {
        "Content-Type": responseContentType,
      },
    });
  } catch {
    return Response.json(
      { detail: "The Agent service is currently unavailable." },
      { status: 502 },
    );
  }
}
