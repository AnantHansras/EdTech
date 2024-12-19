const jwt = require("jsonwebtoken");
const User = require("../models/User");
require("dotenv").config();

//islogin =>auth
exports.auth = async (req,res,next) => {
    try{
        //extract token
        
        const token = req.cookies.token || req.body.token || req.header("Authorization").replace("Bearer ","");
        
        //if token is missing 
        
        if(!token){
            return res.status(401).json({
                success:false,
                message:"Token is missing"
            });
        }
        
        //verify the token
        try{
            const decode = jwt.verify(token,process.env.JWT_SECRET);
            console.log("hiiii")
            console.log(decode);
            req.user = decode;
            
        }
        catch(err){
            return res.status(401).json({
                success:false,
                message:"token is invalid"
            });
        }
        
        
        next();
    }
    catch(err){
        return res.status(401).json({
            success:false,
            message:err.message
        });
    }
}
//isadmin
exports.isAdmin = async (req,res,next) =>{
    try{
        if(req.user.accountType !== "Admin"){
            return res.status(401).json({
                success:false,
                message:"This is protected route for Admin only"
            });
        }
        next();
    }
    catch(err){
        return res.status(401).json({
            success:false,
            message:err.message
        });
    }
}
//isstudent
exports.isStudent = async (req,res,next) =>{
    try{
        if(req.user.accountType !== "Student"){
            return res.status(401).json({
                success:false,
                message:"This is protected route for students only"
            });
        }
        next();
    }
    catch(err){
        return res.status(401).json({
            success:false,
            message:err.message
        });
    }
}
//isinstructor
exports.isInstructor = async (req,res,next) =>{
    try{
        console.log(req.user.accountType)
        if(req.user.accountType !== "Instructor"){
            return res.status(401).json({
                success:false,
                message:"This is protected route for Instructor only"
            });
        }
        next();
    }
    catch(err){
        return res.status(401).json({
            success:false,
            message:err.message
        });
    }
}