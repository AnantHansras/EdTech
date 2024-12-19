const User = require("../models/User");
const mailSender = require("../utils/mailSender");
const bcrypt = require('bcrypt')
const crypto = require("crypto");

//resetPasswordToken
exports.resetPasswordToken = async (req,res) =>{
    try{
        //fetch email from req body
        const {email} = req.body;

        //check if signed up or not
        const user = await User.findOne({email});
        if(!user){
            return res.status(401).json({
                success:false,
                message:"User not registered"
            });
        }

        //generate token
        //const token = crypto.randomUUID();
        const token = crypto.randomBytes(20).toString("hex");
        
        //update user by adding expiry time and token
        const updatedUser = await User.findOneAndUpdate({email},{token:token,resetPasswordExpires: Date.now() + 5*60*1000},{new:true});
        console.log(updatedUser);
        
        //create url of resetpassword page
        const URL = `http://localhost:3000/update-password/${token}`;

        //send URL thru mail
        await mailSender(email,"Password Reset link from Studynotion",URL);

        return res.json({
            success:true,
            message:"Reset Password token generated successfully",
            token
        });
    }
    catch(err){
        return res.status(401).json({
            success:false,
            message:err.message
        });
    }
}

//resetPassword
exports.resetPassword = async (req,res) => {
    try{
        //fetch data from req body
        const {password,confirmPassword,token} = req.body;

        //validate data
        if(password !== confirmPassword){
            return res.status(401).json({
                success:false,
                message:"Password and confirmPassword do not match"
            });
        }

        //get user details from db using token
        const userDetails = await User.findOne({token});

        //if no entry in db => invalid token
        if(!userDetails){
            return res.status(401).json({
                success:false,
                message:"invalid token"
            });
        }

        //token time check
        if(userDetails.resetPasswordExpires < Date.now()){
            return res.json({
                sucess:false,
                message:"Token is expired"
            });
        }

        //hash password
        const hashedPassword = await bcrypt.hash(password,10);

        //password update in db
        await User.findOneAndUpdate({token},{password : hashedPassword},{new:true});

        return res.json({
            success:true,
            message:"Password reset successfully"
        });

    }
    catch(err){
        return res.status(401).json({
            success:false,
            message:err.message
        });
    }
}