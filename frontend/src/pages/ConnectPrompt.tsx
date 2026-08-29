import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";

export default function ConnectPrompt() {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="font-heading text-base">Connect your Garmin account</CardTitle>
        <CardDescription>Link your Garmin Connect account to see your training data here.</CardDescription>
      </CardHeader>
      <CardContent>
        <Button asChild size="sm">
          <a href="/connect-garmin">Connect Garmin</a>
        </Button>
      </CardContent>
    </Card>
  );
}
