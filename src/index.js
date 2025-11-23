import express from "express";
import authRouter from "./routes/auth.js";
import cors from "cors";

const app = express();

app.use(cors());
app.use(express.json());

app.use("/auth", authRouter);

app.get("/", (req, res) => res.send("API ONLINE"));

app.listen(process.env.PORT || 3000);
